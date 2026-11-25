"""Data exchanged with the LLM.

RecommendationContext  what the backend sends: facts and backend-computed numbers only.
LLMRecommendation      what the LLM must return, validated with Pydantic before any use.

The LLM never does arithmetic that matters: every figure it may quote is in the context,
and its suggested quantity is checked against the backend's bounds before it is saved.
"""

import enum
import json
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from app.ai.client import LLMInvalidResponseError
from app.models.ai_recommendation import RiskLevel
from app.models.inventory_alert import AlertSeverity, AlertType
from app.schemas.sales_analytics import SalesTrend
from app.services.reorder_service import InventoryStatus

# ---------- context sent to the LLM ----------


class ProductContext(BaseModel):
    sku: str
    name: str
    category: str
    unit_cost: Decimal
    current_stock: int
    reorder_point: int
    minimum_stock: int
    reorder_quantity: int = Field(description="Standard order quantity configured for the product")
    inventory_status: InventoryStatus


class SalesContext(BaseModel):
    units_sold_7d: int
    units_sold_30d: int
    average_daily_sales_7d: Decimal
    average_daily_sales_30d: Decimal
    days_remaining: Decimal | None = Field(description="null when there were no sales in 30 days")
    trend: SalesTrend
    daily_units_last_30d: list[int] = Field(description="Units per day, oldest first, today partial")


class SupplierContext(BaseModel):
    """Only what the decision needs; contact details are never sent to the LLM."""

    name: str
    lead_time_days: int
    is_active: bool


class AlertContext(BaseModel):
    alert_type: AlertType
    severity: AlertSeverity


class RiskAssessment(BaseModel):
    """Decided by backend rules (reorder_service.assess_risk); the LLM explains, never changes it."""

    risk_level: RiskLevel
    at_or_below_reorder_point: bool
    at_or_below_minimum_stock: bool
    expected_demand_during_lead_time: Decimal | None = Field(
        description="average_daily_sales_30d x lead_time_days; null without supplier or sales"
    )
    stock_covers_lead_time: bool | None = Field(
        description="current_stock >= expected demand during lead time; null if unknown"
    )


class QuantityGuidance(BaseModel):
    """Backend bounds for suggested_quantity; the response is rejected outside them."""

    min_quantity: int
    max_quantity: int


class RecommendationContext(BaseModel):
    as_of: datetime
    product: ProductContext
    sales: SalesContext
    supplier: SupplierContext | None
    alert: AlertContext | None
    risk: RiskAssessment
    quantity_guidance: QuantityGuidance


# ---------- response expected from the LLM ----------


class Urgency(str, enum.Enum):
    IMMEDIATE = "IMMEDIATE"  # order today
    SOON = "SOON"  # order within the next few days
    ROUTINE = "ROUTINE"  # include in the next regular order
    NONE = "NONE"  # no order needed now


ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)]


class LLMRecommendation(BaseModel):
    """Validated LLM output. Risk level and human approval are decided by the backend,
    so the LLM is not asked for them."""

    model_config = ConfigDict(extra="forbid")

    urgency: Urgency
    recommendation: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)
    ]
    suggested_quantity: int = Field(ge=0)
    reasoning: list[ShortText] = Field(min_length=1, max_length=6)


RECOMMENDATION_SCHEMA_NAME = "inventory_recommendation"


def _enum_values(e: type[enum.Enum]) -> list[str]:
    return [m.value for m in e]


# Sent to the provider for strict structured output. Written by hand and kept to the keywords
# Groq documents for strict mode (every property required, additionalProperties false);
# length limits are enforced by LLMRecommendation instead. A test keeps the two in sync.
RECOMMENDATION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "urgency": {"type": "string", "enum": _enum_values(Urgency)},
        "recommendation": {"type": "string"},
        "suggested_quantity": {"type": "integer"},
        "reasoning": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["urgency", "recommendation", "suggested_quantity", "reasoning"],
    "additionalProperties": False,
}


def parse_recommendation(content: str) -> LLMRecommendation:
    """Parse and validate raw LLM output. Error messages name fields, never echo the content."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMInvalidResponseError("LLM response is not valid JSON") from exc
    try:
        return LLMRecommendation.model_validate(data)
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in err["loc"]) or "<root>" for err in exc.errors()})
        raise LLMInvalidResponseError(
            f"LLM response failed validation: {', '.join(fields)}"
        ) from exc
