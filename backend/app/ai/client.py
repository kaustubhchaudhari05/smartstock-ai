"""LLM client: one small interface, a real OpenAI-compatible implementation and an offline fake.

The client only moves text. It never sees the database and its output is never trusted:
callers must validate the returned JSON before using it (CLAUDE.md section 6).

Provider errors are translated into the LLMError hierarchy below so the rest of the app does
not depend on the openai package. Error messages never include the API key or prompt content.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import openai

from app.core.config import Settings, get_settings


# ---------- errors ----------


class LLMError(Exception):
    """Base class. `retryable` tells callers (e.g. Celery tasks later) whether to try again."""

    retryable = False


class LLMNotConfiguredError(LLMError):
    """No API key, or the provider rejected the key / model."""


class LLMTimeoutError(LLMError):
    retryable = True


class LLMRateLimitError(LLMError):
    retryable = True

    def __init__(self, message: str, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class LLMUnavailableError(LLMError):
    """Network failure or a provider-side (5xx) error."""

    retryable = True


class LLMInvalidResponseError(LLMError):
    """The provider answered, but not with usable JSON (rejected schema, truncated, empty...)."""


# ---------- interface ----------


@dataclass(frozen=True)
class LLMResponse:
    content: str  # raw JSON text, still to be validated by the caller
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMClient(Protocol):
    model_name: str

    def complete_json(
        self, *, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> LLMResponse:
        """Return a JSON document intended to match `schema`, or raise an LLMError."""
        ...


# ---------- OpenAI-compatible implementation (Groq by default) ----------


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return float(response.headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        http_client: httpx.Client | None = None,
    ):
        self.model_name = model
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=max_retries,  # the SDK backs off on 408/429/5xx/connection errors
            http_client=http_client,
        )

    def complete_json(
        self, *, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> LLMResponse:
        try:
            completion = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "schema": schema, "strict": True},
                },
                temperature=0.2,
            )
        except openai.APITimeoutError as exc:  # subclass of APIConnectionError: check first
            raise LLMTimeoutError("LLM request timed out") from exc
        except openai.APIConnectionError as exc:
            raise LLMUnavailableError("Could not reach the LLM service") from exc
        except openai.RateLimitError as exc:
            raise LLMRateLimitError(
                "LLM rate limit reached", retry_after_seconds=_retry_after(exc.response)
            ) from exc
        except (openai.AuthenticationError, openai.PermissionDeniedError, openai.NotFoundError) as exc:
            raise LLMNotConfiguredError(
                f"LLM service rejected the configuration (HTTP {exc.status_code}); "
                "check LLM_API_KEY and LLM_MODEL"
            ) from exc
        except openai.BadRequestError as exc:
            # e.g. Groq's json_validate_failed when the model cannot satisfy the schema
            raise LLMInvalidResponseError(f"LLM request rejected (HTTP {exc.status_code})") from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMUnavailableError(f"LLM service error (HTTP {exc.status_code})") from exc
            raise LLMInvalidResponseError(f"LLM request failed (HTTP {exc.status_code})") from exc

        if not completion.choices:
            raise LLMInvalidResponseError("LLM returned no choices")
        choice = completion.choices[0]
        if choice.finish_reason == "length":
            raise LLMInvalidResponseError("LLM response was truncated")
        content = (choice.message.content or "").strip()
        if not content:
            raise LLMInvalidResponseError("LLM returned an empty response")

        usage = completion.usage
        return LLMResponse(
            content=content,
            model=completion.model or self.model_name,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
        )


# ---------- offline fake ----------

FakeStep = str | LLMError | Callable[[str, str, dict[str, Any]], str]


class FakeLLMClient:
    """Offline stand-in: plays back scripted steps in order (the last one repeats).

    A step is a JSON string to return, an LLMError to raise, or a function
    (system, user, schema) -> JSON string. Every call is recorded in `calls`.
    """

    model_name = "fake"

    def __init__(
        self, steps: Sequence[FakeStep] = ("{}",), *, prompt_tokens: int = 0, completion_tokens: int = 0
    ):
        if not steps:
            raise ValueError("FakeLLMClient needs at least one step")
        self._steps = list(steps)
        self._usage = (prompt_tokens, completion_tokens)
        self.calls: list[dict[str, Any]] = []

    def complete_json(
        self, *, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> LLMResponse:
        self.calls.append({"system": system, "user": user, "schema_name": schema_name, "schema": schema})
        step = self._steps[min(len(self.calls), len(self._steps)) - 1]
        if isinstance(step, LLMError):
            raise step
        content = step(system, user, schema) if callable(step) else step
        return LLMResponse(
            content=content, model=self.model_name,
            prompt_tokens=self._usage[0], completion_tokens=self._usage[1],
        )


# ---------- factory ----------


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    """Client for the configured provider. Raises LLMNotConfiguredError if no key is set."""
    settings = settings or get_settings()
    if settings.llm_provider == "fake":
        return FakeLLMClient()
    api_key = settings.llm_api_key.get_secret_value().strip() if settings.llm_api_key else ""
    if not api_key:
        raise LLMNotConfiguredError("AI service is not configured: set LLM_API_KEY in .env")
    return OpenAICompatibleClient(
        api_key=api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
