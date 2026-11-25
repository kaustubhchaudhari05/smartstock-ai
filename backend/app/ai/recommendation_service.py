"""AI inventory recommendations (CLAUDE.md Workflow 4).

1. Load the product, its supplier and its unresolved alert.
2. Compute every number deterministically (sales metrics, lead-time demand, risk, bounds).
3. Send that context to the LLM and validate its answer against the backend's rules.
4. Save the recommendation (PENDING_REVIEW) together with the exact context it was based on.

Recommendations are decision support only: nothing here changes stock or creates orders.
If the LLM fails, an LLMError is raised and nothing is written; monitoring is unaffected.
"""

import logging
import math
import time
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.ai.client import LLMClient, LLMInvalidResponseError, get_llm_client
from app.ai.prompts import PROMPT_VERSION, build_recommendation_prompt
from app.ai.schemas import (
    RECOMMENDATION_JSON_SCHEMA,
    RECOMMENDATION_SCHEMA_NAME,
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
from app.core.limits import MAX_MOVEMENT_QUANTITY, MAX_STOCK
from app.models import AIRecommendation, InventoryAlert, Product
from app.models.ai_recommendation import RiskLevel, Urgency
from app.models.inventory_alert import AlertStatus
from app.repositories import alert_repository
from app.services import reorder_service, sales_analytics
from app.services.exceptions import BusinessRuleError, NotFoundError

logger = logging.getLogger(__name__)

# Upper bound for a suggested order: the larger of three standard orders or 90 days of demand.
MAX_STANDARD_ORDERS = 3
MAX_DAYS_OF_DEMAND = 90

URGENT_RISKS = {RiskLevel.CRITICAL, RiskLevel.HIGH}
URGENT_ACTIONS = {Urgency.IMMEDIATE, Urgency.SOON}


# ---------- deterministic context ----------


def quantity_bounds(product: Product, average_daily_sales: Decimal) -> QuantityGuidance:
    demand_cap = math.ceil(average_daily_sales * MAX_DAYS_OF_DEMAND)
    upper = max(product.reorder_quantity * MAX_STANDARD_ORDERS, demand_cap, 1)
    upper = min(upper, MAX_MOVEMENT_QUANTITY, MAX_STOCK - product.current_stock)
    return QuantityGuidance(min_quantity=0, max_quantity=max(upper, 0))


def build_context(
    db: Session, product: Product, alert: InventoryAlert | None, as_of: datetime
) -> RecommendationContext:
    metrics = sales_analytics.product_metrics(db, product.id, as_of=as_of)
    supplier = product.supplier
    lead_time = supplier.lead_time_days if supplier else None
    expected = reorder_service.lead_time_demand(metrics.average_daily_sales, lead_time)
    covers = reorder_service.covers_lead_time(product.current_stock, expected)
    return RecommendationContext(
        as_of=as_of,
        product=ProductContext(
            sku=product.sku,
            name=product.name,
            category=product.category,
            unit_cost=product.unit_cost,
            current_stock=product.current_stock,
            reorder_point=product.reorder_point,
            minimum_stock=product.minimum_stock,
            reorder_quantity=product.reorder_quantity,
            inventory_status=reorder_service.classify_stock(
                product.current_stock, product.reorder_point
            ),
        ),
        sales=SalesContext(
            units_sold_7d=metrics.units_sold_7d,
            units_sold_30d=metrics.units_sold_30d,
            average_daily_sales_7d=metrics.average_daily_sales_7d,
            average_daily_sales_30d=metrics.average_daily_sales,
            days_remaining=metrics.days_remaining,
            trend=metrics.trend,
            daily_units_last_30d=[d.units_sold for d in metrics.daily_sales or []],
        ),
        supplier=SupplierContext(
            name=supplier.name, lead_time_days=supplier.lead_time_days, is_active=supplier.is_active
        )
        if supplier
        else None,
        alert=AlertContext(alert_type=alert.alert_type, severity=alert.severity) if alert else None,
        risk=RiskAssessment(
            risk_level=reorder_service.assess_risk(
                product.current_stock, product.reorder_point, product.minimum_stock, covers
            ),
            at_or_below_reorder_point=product.current_stock <= product.reorder_point,
            at_or_below_minimum_stock=product.current_stock <= product.minimum_stock,
            expected_demand_during_lead_time=expected,
            stock_covers_lead_time=covers,
        ),
        quantity_guidance=quantity_bounds(product, metrics.average_daily_sales),
    )


# ---------- validation of the LLM answer ----------


def check_against_context(rec: LLMRecommendation, ctx: RecommendationContext) -> None:
    """Business-rule validation on top of the schema. Raises LLMInvalidResponseError."""
    bounds = ctx.quantity_guidance
    if not bounds.min_quantity <= rec.suggested_quantity <= bounds.max_quantity:
        raise LLMInvalidResponseError(
            f"suggested_quantity {rec.suggested_quantity} is outside the allowed range "
            f"{bounds.min_quantity}-{bounds.max_quantity}"
        )
    if (rec.urgency == Urgency.NONE) != (rec.suggested_quantity == 0):
        raise LLMInvalidResponseError(
            "urgency NONE must go with suggested_quantity 0, and only with it"
        )
    if ctx.risk.risk_level in URGENT_RISKS and rec.urgency not in URGENT_ACTIONS:
        raise LLMInvalidResponseError(
            f"urgency {rec.urgency.value} contradicts risk level {ctx.risk.risk_level.value}"
        )


# ---------- workflow ----------


def _resolve_alert(db: Session, product: Product, alert_id: int | None) -> InventoryAlert | None:
    if alert_id is None:
        unresolved = alert_repository.unresolved_for_product(db, product.id)
        return unresolved[-1] if unresolved else None  # newest
    alert = alert_repository.get_alert(db, alert_id)
    if alert is None:
        raise NotFoundError(f"Alert {alert_id} not found")
    if alert.product_id != product.id:
        raise BusinessRuleError(f"Alert {alert_id} does not belong to product {product.id}")
    if alert.status == AlertStatus.RESOLVED.value:
        raise BusinessRuleError(f"Alert {alert_id} is already resolved")
    return alert


def generate_recommendation(
    db: Session,
    product_id: int,
    *,
    alert_id: int | None = None,
    llm: LLMClient | None = None,
    as_of: datetime | None = None,
) -> AIRecommendation:
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError(f"Product {product_id} not found")
    if not product.is_active:
        raise BusinessRuleError(f"Product {product.sku} is inactive")
    alert = _resolve_alert(db, product, alert_id)
    context = build_context(db, product, alert, as_of or sales_analytics.now_utc())

    llm = llm or get_llm_client()
    system, user = build_recommendation_prompt(context)
    started = time.monotonic()
    try:
        response = llm.complete_json(
            system=system,
            user=user,
            schema_name=RECOMMENDATION_SCHEMA_NAME,
            schema=RECOMMENDATION_JSON_SCHEMA,
        )
        rec = parse_recommendation(response.content)
        check_against_context(rec, context)
    except Exception as exc:
        # type and message only: never the prompt, the response or the API key
        logger.warning(
            "AI recommendation failed for product %s: %s: %s", product.id, type(exc).__name__, exc
        )
        raise

    recommendation = AIRecommendation(
        product_id=product.id,
        alert_id=alert.id if alert else None,
        recommendation=rec.recommendation,
        suggested_quantity=rec.suggested_quantity,
        risk_level=context.risk.risk_level.value,  # backend decision, not the LLM's
        urgency=rec.urgency.value,
        reasoning="\n".join(" ".join(point.split()) for point in rec.reasoning),
        model_name=response.model,
        prompt_version=PROMPT_VERSION,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        context=context.model_dump(mode="json"),
    )
    db.add(recommendation)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(recommendation)
    logger.info(
        "AI recommendation %s for product %s: risk=%s qty=%s model=%s tokens=%s+%s in %.1fs",
        recommendation.id, product.id, recommendation.risk_level, recommendation.suggested_quantity,
        response.model, response.prompt_tokens, response.completion_tokens,
        time.monotonic() - started,
    )
    return recommendation
