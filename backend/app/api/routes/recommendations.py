from typing import Annotated

from fastapi import APIRouter, Query, status

from app.ai import recommendation_service
from app.api.deps import DbSession
from app.models import RecommendationStatus, RiskLevel
from app.schemas.recommendation import (
    RecommendationDetail,
    RecommendationGenerate,
    RecommendationRead,
)

router = APIRouter(prefix="/ai/recommendations", tags=["ai recommendations"])


@router.post("/generate", response_model=RecommendationDetail, status_code=status.HTTP_201_CREATED)
def generate_recommendation(data: RecommendationGenerate, db: DbSession):
    """Ask the LLM for a replenishment recommendation for one active product.

    Risk level, metrics and quantity bounds are computed by the backend; the LLM's answer is
    validated before it is saved as PENDING_REVIEW. Nothing is ordered and stock is unchanged.
    AI failures: 503 not configured / unavailable, 504 timeout, 429 rate limited, 502 invalid answer.
    """
    rec = recommendation_service.generate_recommendation(
        db, data.product_id, alert_id=data.alert_id
    )
    return recommendation_service.get_recommendation(db, rec.id)


@router.get("", response_model=list[RecommendationRead])
def list_recommendations(
    db: DbSession,
    product_id: int | None = None,
    status: RecommendationStatus | None = None,
    risk_level: RiskLevel | None = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    return recommendation_service.list_recommendations(
        db,
        product_id=product_id,
        status=status.value if status else None,
        risk_level=risk_level.value if risk_level else None,
        skip=skip,
        limit=limit,
    )


@router.get("/{recommendation_id}", response_model=RecommendationDetail)
def get_recommendation(recommendation_id: int, db: DbSession):
    return recommendation_service.get_recommendation(db, recommendation_id)
