import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.ai.client import LLMInvalidResponseError
from app.ai.prompts import PROMPT_VERSION, build_recommendation_prompt
from app.ai.schemas import (
    RECOMMENDATION_JSON_SCHEMA,
    AlertContext,
    LLMRecommendation,
    ProductContext,
    QuantityGuidance,
    RecommendationContext,
    RiskAssessment,
    SalesContext,
    SupplierContext,
    parse_recommendation,
)

VALID = {
    "urgency": "IMMEDIATE",
    "recommendation": "Order 100 units today.",
    "suggested_quantity": 100,
    "reasoning": ["Stock 12 is below the reorder point 20.", "About 2.0 days remaining."],
}


def context(**overrides):
    base = dict(
        as_of=datetime(2026, 11, 25, 9, 0, tzinfo=timezone.utc),
        product=ProductContext(
            sku="WM-001", name="Wireless Mouse", category="Electronics", unit_cost=Decimal("8.50"),
            current_stock=12, reorder_point=20, minimum_stock=10, reorder_quantity=100,
            inventory_status="LOW_STOCK"),
        sales=SalesContext(
            units_sold_7d=49, units_sold_30d=179, average_daily_sales_7d=Decimal("7.00"),
            average_daily_sales_30d=Decimal("5.97"), days_remaining=Decimal("2.0"),
            trend="INCREASING", daily_units_last_30d=[6] * 30),
        supplier=SupplierContext(name="TechSupply Co", lead_time_days=5, is_active=True),
        alert=AlertContext(alert_type="LOW_STOCK", severity="MEDIUM"),
        risk=RiskAssessment(
            risk_level="CRITICAL", at_or_below_reorder_point=True, at_or_below_minimum_stock=False,
            expected_demand_during_lead_time=Decimal("29.85"), stock_covers_lead_time=False),
        quantity_guidance=QuantityGuidance(min_quantity=0, max_quantity=400),
    )
    return RecommendationContext(**{**base, **overrides})


def test_valid_response_is_parsed_and_trimmed():
    rec = parse_recommendation(json.dumps({**VALID, "recommendation": "  Order now.  "}))
    assert (rec.urgency, rec.suggested_quantity) == ("IMMEDIATE", 100)
    assert rec.recommendation == "Order now."


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"risk_level": "LOW"}, "risk_level"),  # decided by the backend, not accepted from the LLM
        ({"urgency": "LATER"}, "urgency"),
        ({"suggested_quantity": -5}, "suggested_quantity"),
        ({"suggested_quantity": 12.5}, "suggested_quantity"),
        ({"suggested_quantity": "100"}, None),  # numeric string accepted by lax mode
        ({"recommendation": "   "}, "recommendation"),
        ({"recommendation": "x" * 601}, "recommendation"),
        ({"reasoning": []}, "reasoning"),
        ({"reasoning": ["ok", ""]}, "reasoning.1"),
        ({"reasoning": ["r"] * 7}, "reasoning"),
        ({"requires_human_approval": False}, "requires_human_approval"),  # extra field
    ],
)
def test_invalid_fields_are_rejected(change, field):
    content = json.dumps({**VALID, **change})
    if field is None:
        assert parse_recommendation(content).suggested_quantity == 100
        return
    with pytest.raises(LLMInvalidResponseError) as exc_info:
        parse_recommendation(content)
    assert field in str(exc_info.value)


def test_missing_field_and_non_json():
    with pytest.raises(LLMInvalidResponseError, match="reasoning"):
        parse_recommendation(json.dumps({k: v for k, v in VALID.items() if k != "reasoning"}))
    for bad in ("not json", "", "[1, 2]", '```json\n{"a": 1}\n```'):
        with pytest.raises(LLMInvalidResponseError):
            parse_recommendation(bad)


def test_error_message_does_not_echo_content():
    with pytest.raises(LLMInvalidResponseError) as exc_info:
        parse_recommendation(json.dumps({**VALID, "recommendation": "SECRET-TEXT" * 100}))
    assert "SECRET-TEXT" not in str(exc_info.value)


def test_json_schema_matches_pydantic_model():
    schema = RECOMMENDATION_JSON_SCHEMA
    fields = set(LLMRecommendation.model_fields)
    assert set(schema["properties"]) == fields == set(schema["required"])
    assert schema["additionalProperties"] is False
    model_schema = LLMRecommendation.model_json_schema()
    assert schema["properties"]["urgency"]["enum"] == model_schema["$defs"]["Urgency"]["enum"]


def test_prompt_contains_only_supplied_facts():
    system, user = build_recommendation_prompt(context())
    assert "Use only the supplied data" in system
    assert "min_quantity" in system and "max_quantity" in system
    payload = json.loads(user[user.index("{"):])
    assert payload["product"]["sku"] == "WM-001"
    assert payload["product"]["unit_cost"] == "8.50"  # exact decimal, not a float
    assert payload["risk"] == {
        "risk_level": "CRITICAL", "at_or_below_reorder_point": True, "at_or_below_minimum_stock": False,
        "expected_demand_during_lead_time": "29.85", "stock_covers_lead_time": False}
    assert payload["quantity_guidance"] == {"min_quantity": 0, "max_quantity": 400}
    assert set(payload["supplier"]) == {"name", "lead_time_days", "is_active"}  # no contact details
    assert PROMPT_VERSION


def test_prompt_without_supplier_or_alert():
    ctx = context(supplier=None, alert=None, risk=RiskAssessment(
        risk_level="HIGH", at_or_below_reorder_point=True, at_or_below_minimum_stock=True,
        expected_demand_during_lead_time=None, stock_covers_lead_time=None))
    payload = json.loads(build_recommendation_prompt(ctx)[1].split("\n\n", 1)[1])
    assert payload["supplier"] is None and payload["alert"] is None
    assert payload["risk"]["stock_covers_lead_time"] is None
