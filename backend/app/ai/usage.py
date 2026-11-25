"""Token usage and cost logging for LLM calls.

One INFO/WARNING line per attempt, e.g.
    llm_call purpose=recommendation product_id=1 attempt=1 outcome=ok model=openai/gpt-oss-20b
    latency_ms=1380 prompt_tokens=1138 completion_tokens=524 cost_usd=0.000000
Never logs prompts, responses or keys. Cost uses LLM_*_COST_PER_MILLION (0 on a free plan).
"""

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.core.config import Settings, get_settings

logger = logging.getLogger("app.ai.usage")

MILLION = Decimal(1_000_000)
MICRO_USD = Decimal("0.000001")


def estimate_cost(
    prompt_tokens: int | None, completion_tokens: int | None, settings: Settings | None = None
) -> Decimal:
    settings = settings or get_settings()
    cost = (
        Decimal(prompt_tokens or 0) * settings.llm_input_cost_per_million
        + Decimal(completion_tokens or 0) * settings.llm_output_cost_per_million
    ) / MILLION
    return cost.quantize(MICRO_USD, rounding=ROUND_HALF_UP)


@dataclass
class UsageTotals:
    """Tokens summed over every attempt of one request (failed attempts cost tokens too)."""

    attempts: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reported: bool = False  # False if the provider never reported usage

    def add(self, prompt_tokens: int | None, completion_tokens: int | None) -> None:
        if prompt_tokens is not None or completion_tokens is not None:
            self.reported = True
        self.prompt_tokens += prompt_tokens or 0
        self.completion_tokens += completion_tokens or 0


def log_llm_call(
    *,
    purpose: str,
    product_id: int,
    attempt: int,
    outcome: str,
    model: str,
    latency_seconds: float,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    error: Exception | None = None,
) -> None:
    fields = {
        "purpose": purpose,
        "product_id": product_id,
        "attempt": attempt,
        "outcome": outcome,
        "model": model,
        "latency_ms": round(latency_seconds * 1000),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_usd": estimate_cost(prompt_tokens, completion_tokens),
    }
    if error is not None:
        # our own error messages only: they name fields/limits, never prompt or response text
        fields["error"] = f"{type(error).__name__}: {error}"
    line = " ".join(f"{k}={v}" for k, v in fields.items())
    logger.log(logging.INFO if outcome == "ok" else logging.WARNING, "llm_call %s", line)
