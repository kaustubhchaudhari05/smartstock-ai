import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.ai import recommendation_service
from app.ai.client import (
    FakeLLMClient,
    LLMInvalidResponseError,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.models import AIRecommendation, Product, Sale
from app.services import alert_service

ANSWER = json.dumps({
    "urgency": "IMMEDIATE",
    "recommendation": "Order 120 units of Wireless Mouse today.",
    "suggested_quantity": 120,
    "reasoning": ["Stock of 12 is below the reorder point of 20.", "Stock runs out before delivery."],
})


@pytest.fixture
def use_llm(monkeypatch):
    """Install a FakeLLMClient with the given steps as the configured client."""

    def install(*steps):
        fake = FakeLLMClient(list(steps))
        monkeypatch.setattr(recommendation_service, "get_llm_client", lambda: fake)
        return fake

    return install


@pytest.fixture
def selling_product(db, product):
    now = datetime.now(timezone.utc)
    for i in range(30):
        db.add(Sale(product_id=product.id, quantity_sold=5, unit_price=Decimal("15.99"),
                    sale_date=now - timedelta(hours=1 + 24 * i)))
    alert_service.check_product(db, product)
    db.commit()
    return product


def generate(client, product_id, **extra):
    return client.post("/api/ai/recommendations/generate", json={"product_id": product_id, **extra})


def test_generate_returns_saved_recommendation(client, db, selling_product, use_llm):
    use_llm(ANSWER)
    res = generate(client, selling_product.id)
    assert res.status_code == 201
    body = res.json()
    assert (body["product_sku"], body["risk_level"], body["urgency"], body["suggested_quantity"]) == (
        "WM-001", "CRITICAL", "IMMEDIATE", 120)
    assert body["reasoning"] == ["Stock of 12 is below the reorder point of 20.", "Stock runs out before delivery."]
    assert body["status"] == "PENDING_REVIEW" and body["alert_id"] is not None
    assert body["context"]["risk"]["stock_covers_lead_time"] is False
    assert body["context"]["quantity_guidance"] == {"min_quantity": 0, "max_quantity": 450}
    assert body["prompt_version"] and body["model_name"] == "fake"

    detail = client.get(f"/api/ai/recommendations/{body['id']}").json()
    assert detail == body


def test_list_newest_first_with_filters(client, db, selling_product, supplier, use_llm):
    healthy = Product(sku="SRV-304", name="Servo", category="Components", current_stock=500,
                      reorder_point=15, minimum_stock=8, reorder_quantity=50, unit_cost=Decimal("3.20"),
                      supplier=supplier)
    db.add(healthy)
    db.commit()
    use_llm(ANSWER, json.dumps({"urgency": "NONE", "recommendation": "No order needed.",
                                "suggested_quantity": 0, "reasoning": ["Stock is healthy."]}))
    first = generate(client, selling_product.id).json()
    second = generate(client, healthy.id).json()

    items = client.get("/api/ai/recommendations").json()
    assert [i["id"] for i in items] == [second["id"], first["id"]]
    assert "context" not in items[0]  # list stays light; details carry the snapshot
    assert items[0]["product_name"] == "Servo"

    def ids(**params):
        return [i["id"] for i in client.get("/api/ai/recommendations", params=params).json()]

    assert ids(product_id=selling_product.id) == [first["id"]]
    assert ids(risk_level="LOW") == [second["id"]]
    assert ids(status="PENDING_REVIEW", limit=1) == [second["id"]]
    assert ids(status="ACCEPTED") == []
    assert client.get("/api/ai/recommendations", params={"risk_level": "EXTREME"}).status_code == 422


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (LLMNotConfiguredError("AI service is not configured: set LLM_API_KEY in .env"), 503,
         "AI service is not configured: set LLM_API_KEY in .env"),
        (LLMUnavailableError("Could not reach the LLM service"), 503, "Could not reach the LLM service"),
        (LLMTimeoutError("LLM request timed out"), 504, "LLM request timed out"),
        (LLMRateLimitError("LLM rate limit reached", retry_after_seconds=7.4), 429, "LLM rate limit reached"),
        (LLMInvalidResponseError("LLM response is not valid JSON"), 502, "LLM response is not valid JSON"),
    ],
)
def test_ai_failures_map_to_clear_statuses(client, db, selling_product, use_llm, error, status, detail):
    use_llm(error)
    res = generate(client, selling_product.id)
    assert res.status_code == status
    assert res.json() == {"detail": detail}
    if status == 429:
        assert res.headers["retry-after"] == "7"
    assert db.scalar(select(func.count()).select_from(AIRecommendation)) == 0


def test_rejected_answer_is_502(client, selling_product, use_llm):
    use_llm(json.dumps({**json.loads(ANSWER), "suggested_quantity": 5000}))
    res = generate(client, selling_product.id)
    assert res.status_code == 502
    assert "outside the allowed range 0-450" in res.json()["detail"]


def test_no_key_configured_is_503(client, selling_product):
    # conftest's guard stands in for the real factory; the real one raises the same error type
    res = generate(client, selling_product.id)
    assert res.status_code == 503


def test_request_validation_and_business_errors(client, db, selling_product, use_llm):
    fake = use_llm(ANSWER)
    assert generate(client, 999999).status_code == 404
    assert generate(client, selling_product.id, alert_id=999999).status_code == 404
    assert client.post("/api/ai/recommendations/generate", json={}).status_code == 422
    assert generate(client, selling_product.id, quantity=5).status_code == 422  # extra field
    # Swagger's old pre-filled body: ids must be positive (422, not a misleading 404)
    assert client.post("/api/ai/recommendations/generate",
                       json={"product_id": 0, "alert_id": 0}).status_code == 422
    assert generate(client, selling_product.id, alert_id=0).status_code == 422
    client.delete(f"/api/products/{selling_product.id}")
    res = generate(client, selling_product.id)
    assert res.status_code == 422 and "inactive" in res.json()["detail"]
    assert fake.calls == []  # never reached the LLM


def test_unknown_recommendation(client):
    res = client.get("/api/ai/recommendations/999999")
    assert res.status_code == 404
    assert res.json() == {"detail": "Recommendation 999999 not found"}
