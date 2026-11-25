"""LLM client tests. No network: the real OpenAI SDK talks to an httpx MockTransport."""

import json

import httpx
import pytest

from app.ai.client import (
    FakeLLMClient,
    LLMInvalidResponseError,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
    OpenAICompatibleClient,
    get_llm_client,
)
from app.core.config import Settings

SCHEMA = {
    "type": "object",
    "properties": {"risk_level": {"type": "string"}},
    "required": ["risk_level"],
    "additionalProperties": False,
}
SECRET = "gsk_test_secret_value"


def completion(content, finish_reason="stop"):
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "openai/gpt-oss-20b",
        "choices": [
            {"index": 0, "finish_reason": finish_reason,
             "message": {"role": "assistant", "content": content}}
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
    }


def make_client(handler, max_retries=0):
    return OpenAICompatibleClient(
        api_key=SECRET,
        base_url="https://llm.test/openai/v1",
        model="openai/gpt-oss-20b",
        timeout_seconds=5,
        max_retries=max_retries,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def call(client):
    return client.complete_json(system="sys", user="usr", schema_name="rec", schema=SCHEMA)


def test_successful_call_sends_strict_schema_and_reads_usage():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=completion('{"risk_level": "HIGH"}'))

    res = call(make_client(handler))
    assert (res.content, res.model, res.prompt_tokens, res.completion_tokens) == (
        '{"risk_level": "HIGH"}', "openai/gpt-oss-20b", 120, 30)
    assert seen["url"] == "https://llm.test/openai/v1/chat/completions"
    assert seen["auth"] == f"Bearer {SECRET}"
    body = seen["body"]
    assert body["model"] == "openai/gpt-oss-20b"
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["response_format"] == {
        "type": "json_schema", "json_schema": {"name": "rec", "schema": SCHEMA, "strict": True}}


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (429, LLMRateLimitError),
        (500, LLMUnavailableError),
        (503, LLMUnavailableError),
        (401, LLMNotConfiguredError),
        (404, LLMNotConfiguredError),
        (400, LLMInvalidResponseError),
        (422, LLMInvalidResponseError),
    ],
)
def test_http_errors_are_translated(status, error):
    handler = lambda request: httpx.Response(
        status, json={"error": {"message": "boom", "type": "x"}}, headers={"retry-after": "7"})
    with pytest.raises(error) as exc_info:
        call(make_client(handler))
    assert SECRET not in str(exc_info.value)
    if status == 429:
        assert exc_info.value.retry_after_seconds == 7
        assert exc_info.value.retryable


def test_timeout_and_connection_errors():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LLMTimeoutError):
        call(make_client(timeout))
    with pytest.raises(LLMUnavailableError):
        call(make_client(refused))


def test_sdk_retries_transient_errors():
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(503, json={"error": {"message": "busy"}}, headers={"retry-after": "0"})
        return httpx.Response(200, json=completion('{"risk_level": "LOW"}'))

    assert call(make_client(handler, max_retries=1)).content == '{"risk_level": "LOW"}'
    assert len(attempts) == 2


@pytest.mark.parametrize(
    ("content", "finish_reason"),
    [("", "stop"), (None, "stop"), ("   ", "stop"), ('{"risk_le', "length")],
)
def test_unusable_responses(content, finish_reason):
    handler = lambda request: httpx.Response(200, json=completion(content, finish_reason))
    with pytest.raises(LLMInvalidResponseError):
        call(make_client(handler))


def test_fake_client_plays_steps_in_order_and_repeats_the_last():
    fake = FakeLLMClient(['{"a": 1}', LLMTimeoutError("t"), lambda s, u, schema: json.dumps({"user": u})])
    assert call(fake).content == '{"a": 1}'
    with pytest.raises(LLMTimeoutError):
        call(fake)
    assert call(fake).content == '{"user": "usr"}'
    assert call(fake).content == '{"user": "usr"}'
    assert len(fake.calls) == 4 and fake.calls[0]["schema_name"] == "rec"


def settings(**overrides):
    # explicit values so the developer's real .env cannot affect the result
    base = dict(database_url="postgresql+psycopg://x@localhost/x", llm_provider="openai_compatible",
                llm_api_key=None)
    return Settings(**{**base, **overrides})


def test_factory():
    with pytest.raises(LLMNotConfiguredError, match="LLM_API_KEY"):
        get_llm_client(settings())
    with pytest.raises(LLMNotConfiguredError):
        get_llm_client(settings(llm_api_key="   "))
    assert isinstance(get_llm_client(settings(llm_provider="fake")), FakeLLMClient)
    client = get_llm_client(settings(llm_api_key=SECRET))
    assert isinstance(client, OpenAICompatibleClient)
    assert client.model_name == "openai/gpt-oss-20b"  # Groq default
    assert SECRET not in repr(settings(llm_api_key=SECRET))  # SecretStr hides it
