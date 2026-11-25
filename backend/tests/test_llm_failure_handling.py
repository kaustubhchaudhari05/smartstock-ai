"""Phase 5 failure handling: invalid-answer retries, token totals, usage and cost logging."""

import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.ai import recommendation_service as svc
from app.ai.client import (
    FakeLLMClient,
    LLMInvalidResponseError,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.ai.usage import UsageTotals, estimate_cost
from app.core.config import Settings, get_settings
from app.models import AIRecommendation, InventoryAlert, Sale
from app.services import alert_service

AS_OF = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
VALID = {
    "urgency": "IMMEDIATE",
    "recommendation": "Order 120 units today.",
    "suggested_quantity": 120,
    "reasoning": ["Stock of 12 is below the reorder point of 20."],
}
GOOD = json.dumps(VALID)
TOO_MANY = json.dumps({**VALID, "suggested_quantity": 5000})  # max allowed is 450


@pytest.fixture
def selling_product(db, product):
    for i in range(30):
        db.add(Sale(product_id=product.id, quantity_sold=5, unit_price=Decimal("15.99"),
                    sale_date=AS_OF - timedelta(hours=1 + 24 * i)))
    alert_service.check_product(db, product)
    db.commit()
    return product


def generate(db, product, fake):
    return svc.generate_recommendation(db, product.id, llm=fake, as_of=AS_OF)


def saved(db):
    return db.scalar(select(func.count()).select_from(AIRecommendation))


def with_settings(monkeypatch, **overrides):
    monkeypatch.setattr(svc, "get_settings", lambda: get_settings().model_copy(update=overrides))


def test_rejected_answer_is_retried_with_the_reason(db, selling_product):
    fake = FakeLLMClient([TOO_MANY, GOOD], prompt_tokens=1000, completion_tokens=400)
    rec = generate(db, selling_product, fake)

    assert rec.suggested_quantity == 120
    assert len(fake.calls) == 2
    first, second = (c["user"] for c in fake.calls)
    assert "rejected" not in first
    assert "Your previous answer was rejected: suggested_quantity 5000 is outside the allowed range 0-450" in second
    # failed attempts cost tokens too: stored usage is the total
    assert (rec.prompt_tokens, rec.completion_tokens) == (2000, 800)


def test_provider_side_validation_failure_is_retried(db, selling_product):
    # e.g. Groq's HTTP 400 json_validate_failed: no usage reported for that attempt
    fake = FakeLLMClient([LLMInvalidResponseError("LLM request rejected (HTTP 400)"), GOOD],
                         prompt_tokens=1000, completion_tokens=400)
    rec = generate(db, selling_product, fake)
    assert len(fake.calls) == 2
    assert (rec.prompt_tokens, rec.completion_tokens) == (1000, 400)


def test_gives_up_after_the_configured_retries(db, selling_product):
    fake = FakeLLMClient([TOO_MANY])
    with pytest.raises(LLMInvalidResponseError, match="outside the allowed range"):
        generate(db, selling_product, fake)
    assert len(fake.calls) == 2  # 1 + LLM_INVALID_RESPONSE_RETRIES (default 1)
    assert saved(db) == 0
    assert db.scalar(select(func.count()).select_from(InventoryAlert)) == 1  # monitoring intact


@pytest.mark.parametrize("retries", [0, 3])
def test_retry_count_is_configurable(db, selling_product, monkeypatch, retries):
    with_settings(monkeypatch, llm_invalid_response_retries=retries)
    fake = FakeLLMClient([TOO_MANY])
    with pytest.raises(LLMInvalidResponseError):
        generate(db, selling_product, fake)
    assert len(fake.calls) == 1 + retries


@pytest.mark.parametrize(
    "error",
    [LLMTimeoutError("t"), LLMRateLimitError("r"), LLMUnavailableError("u"), LLMNotConfiguredError("n")],
)
def test_transport_and_config_errors_are_not_re_asked(db, selling_product, error):
    # transport retries/backoff happen inside the SDK; asking again here would multiply them
    fake = FakeLLMClient([error, GOOD])
    with pytest.raises(type(error)):
        generate(db, selling_product, fake)
    assert len(fake.calls) == 1
    assert saved(db) == 0


def test_usage_not_reported_is_stored_as_null(db, selling_product):
    class NoUsage(FakeLLMClient):
        def complete_json(self, **kwargs):
            return super().complete_json(**kwargs).__class__(content=GOOD, model="fake")

    rec = generate(db, selling_product, NoUsage([GOOD]))
    assert (rec.prompt_tokens, rec.completion_tokens) == (None, None)


def test_every_attempt_is_logged_without_sensitive_content(db, selling_product, caplog):
    caplog.set_level(logging.INFO, logger="app.ai.usage")
    fake = FakeLLMClient([TOO_MANY, GOOD], prompt_tokens=1138, completion_tokens=524)
    generate(db, selling_product, fake)

    lines = [r for r in caplog.records if r.name == "app.ai.usage"]
    assert [r.levelname for r in lines] == ["WARNING", "INFO"]
    invalid, ok = (r.getMessage() for r in lines)
    assert invalid.startswith("llm_call purpose=recommendation product_id=")
    assert "attempt=1 outcome=invalid model=fake" in invalid
    assert "prompt_tokens=1138 completion_tokens=524 cost_usd=0.000000" in invalid
    assert "error=LLMInvalidResponseError: suggested_quantity 5000" in invalid
    assert "attempt=2 outcome=ok" in ok and "latency_ms=" in ok
    everything = caplog.text
    for secret in ("WM-001", "Wireless Mouse", "Order 120 units", "Acme Peripherals"):
        assert secret not in everything  # no prompt or response content


def test_error_attempts_are_logged(db, selling_product, caplog):
    caplog.set_level(logging.INFO, logger="app.ai.usage")
    with pytest.raises(LLMTimeoutError):
        generate(db, selling_product, FakeLLMClient([LLMTimeoutError("LLM request timed out")]))
    (line,) = [r.getMessage() for r in caplog.records if r.name == "app.ai.usage"]
    assert "outcome=error" in line and "error=LLMTimeoutError: LLM request timed out" in line
    assert "prompt_tokens=None" in line


def test_estimate_cost():
    paid = Settings(database_url="postgresql+psycopg://x@localhost/x",
                    llm_input_cost_per_million=Decimal("0.10"), llm_output_cost_per_million=Decimal("0.50"))
    # (1138 x 0.10 + 524 x 0.50) / 1M = 0.0003758 -> rounded to micro-dollars
    assert estimate_cost(1138, 524, paid) == Decimal("0.000376")
    assert estimate_cost(None, None, paid) == Decimal("0.000000")
    free = Settings(database_url="postgresql+psycopg://x@localhost/x",
                    llm_input_cost_per_million=Decimal("0"), llm_output_cost_per_million=Decimal("0"))
    assert estimate_cost(1_000_000, 1_000_000, free) == Decimal("0.000000")


def test_usage_totals():
    totals = UsageTotals()
    assert not totals.reported
    totals.add(None, None)
    assert not totals.reported
    totals.add(10, 5)
    totals.add(None, 7)
    assert (totals.prompt_tokens, totals.completion_tokens, totals.reported) == (10, 12, True)
