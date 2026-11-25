"""AI inventory recommendations (CLAUDE.md Workflow 4).

1. Load the product, its supplier and its unresolved alert.
2. Compute every number deterministically (sales metrics, lead-time demand, risk, bounds).
3. Send that context to the LLM and validate its answer against the backend's rules.
4. Save the recommendation (PENDING_REVIEW) together with the exact context it was based on.

Recommendations are decision support only: nothing here changes stock or creates orders.
If the LLM fails, an LLMError is raised and nothing is written; monitoring is unaffected.

Failure handling: transport problems (timeouts, 429, 5xx) are retried with backoff by the SDK
(LLM_MAX_RETRIES). An unusable answer (invalid JSON, schema or business-rule violation) is
re-asked up to LLM_INVALID_RESPONSE_RETRIES times, telling the model why it was rejected.
Every attempt is logged with its token usage and estimated cost (app.ai.usage).
"""

import logging
import math
import time
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.ai.client import LLMClient, LLMError, LLMInvalidResponseError, LLMResponse, get_llm_client
from app.ai.prompts import PROMPT_VERSION, build_recommendation_prompt
from app.ai.usage import UsageTotals, log_llm_call
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
from app.core.config import get_settings
from app.core.limits import MAX_MOVEMENT_QUANTITY, MAX_STOCK
from app.models import AIRecommendation, InventoryAlert, Product
from app.models.ai_recommendation import RiskLevel, Urgency
from app.models.inventory_alert import AlertStatus
from app.repositories import alert_repository, recommendation_repository
from app.schemas.recommendation import RecommendationDetail, RecommendationRead
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
    started = time.monotonic()
    rec, response, usage = _ask_llm(llm, context, product.id)

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
        # summed over all attempts, so stored usage matches what the provider billed
        prompt_tokens=usage.prompt_tokens if usage.reported else None,
        completion_tokens=usage.completion_tokens if usage.reported else None,
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
        "AI recommendation %s saved for product %s: risk=%s qty=%s attempts=%s tokens=%s+%s in %.1fs",
        recommendation.id, product.id, recommendation.risk_level, recommendation.suggested_quantity,
        usage.attempts, usage.prompt_tokens, usage.completion_tokens, time.monotonic() - started,
    )
    return recommendation


def _ask_llm(
    llm: LLMClient, context: RecommendationContext, product_id: int
) -> tuple[LLMRecommendation, LLMResponse, UsageTotals]:
    """Call the LLM until it gives a valid answer or the invalid-answer retries run out.

    Only LLMInvalidResponseError is retried here; other LLMErrors (already retried by the SDK
    where that makes sense) are raised immediately.
    """
    system, base_user = build_recommendation_prompt(context)
    max_attempts = 1 + get_settings().llm_invalid_response_retries
    usage = UsageTotals()
    rejection: LLMInvalidResponseError | None = None

    for attempt in range(1, max_attempts + 1):
        user = base_user
        if rejection is not None:
            user += (
                f"\n\nYour previous answer was rejected: {rejection}. "
                "Return a corrected JSON object that follows all rules."
            )
        usage.attempts = attempt
        call_started = time.monotonic()
        log = dict(purpose="recommendation", product_id=product_id, attempt=attempt,
                   model=llm.model_name)
        try:
            response = llm.complete_json(
                system=system,
                user=user,
                schema_name=RECOMMENDATION_SCHEMA_NAME,
                schema=RECOMMENDATION_JSON_SCHEMA,
            )
        except LLMInvalidResponseError as exc:  # e.g. provider-side schema validation failure
            log_llm_call(**log, outcome="invalid", latency_seconds=time.monotonic() - call_started,
                         error=exc)
            rejection = exc
            continue
        except LLMError as exc:
            log_llm_call(**log, outcome="error", latency_seconds=time.monotonic() - call_started,
                         error=exc)
            raise

        usage.add(response.prompt_tokens, response.completion_tokens)
        log.update(model=response.model, latency_seconds=time.monotonic() - call_started,
                   prompt_tokens=response.prompt_tokens, completion_tokens=response.completion_tokens)
        try:
            rec = parse_recommendation(response.content)
            check_against_context(rec, context)
        except LLMInvalidResponseError as exc:
            log_llm_call(**log, outcome="invalid", error=exc)
            rejection = exc
            continue
        log_llm_call(**log, outcome="ok")
        return rec, response, usage

    assert rejection is not None
    raise rejection


# ---------- reads ----------


def _read_fields(rec: AIRecommendation) -> dict:
    return dict(
        id=rec.id,
        product_id=rec.product_id,
        product_sku=rec.product.sku,
        product_name=rec.product.name,
        alert_id=rec.alert_id,
        risk_level=rec.risk_level,
        urgency=rec.urgency,
        recommendation=rec.recommendation,
        suggested_quantity=rec.suggested_quantity,
        reasoning=rec.reasoning.splitlines(),
        status=rec.status,
        model_name=rec.model_name,
        created_at=rec.created_at,
    )


def to_read(rec: AIRecommendation) -> RecommendationRead:
    return RecommendationRead(**_read_fields(rec))


def to_detail(rec: AIRecommendation) -> RecommendationDetail:
    return RecommendationDetail(
        **_read_fields(rec),
        prompt_version=rec.prompt_version,
        prompt_tokens=rec.prompt_tokens,
        completion_tokens=rec.completion_tokens,
        context=rec.context,
    )


def list_recommendations(db: Session, **filters) -> list[RecommendationRead]:
    return [to_read(r) for r in recommendation_repository.list_recommendations(db, **filters)]


def get_recommendation(db: Session, recommendation_id: int) -> RecommendationDetail:
    rec = recommendation_repository.get_recommendation(db, recommendation_id)
    if rec is None:
        raise NotFoundError(f"Recommendation {recommendation_id} not found")
    return to_detail(rec)
