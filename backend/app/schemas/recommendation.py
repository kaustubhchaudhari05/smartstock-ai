from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RecommendationGenerate(BaseModel):
    # Example shown in Swagger: without it, "Try it out" pre-fills alert_id 0 -> "Alert 0 not found".
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"product_id": 1}]})

    product_id: int = Field(gt=0)
    alert_id: int | None = Field(
        default=None,
        gt=0,
        description="Optional: an unresolved alert of this product. Omit it to use the "
        "product's newest unresolved alert.",
    )


class RecommendationRead(BaseModel):
    id: int
    product_id: int
    product_sku: str
    product_name: str
    alert_id: int | None
    risk_level: str = Field(description="Decided by backend rules, not by the LLM")
    urgency: str
    recommendation: str
    suggested_quantity: int
    reasoning: list[str]
    status: str
    model_name: str
    created_at: datetime


class RecommendationDetail(RecommendationRead):
    prompt_version: str
    prompt_tokens: int | None
    completion_tokens: int | None
    context: dict[str, Any] = Field(
        description="Exact backend-computed data the LLM was given (snapshot at generation time)"
    )
