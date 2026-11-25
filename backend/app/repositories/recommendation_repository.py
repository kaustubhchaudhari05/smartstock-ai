from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import AIRecommendation


def list_recommendations(
    db: Session,
    *,
    product_id: int | None = None,
    status: str | None = None,
    risk_level: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> Sequence[AIRecommendation]:
    stmt = select(AIRecommendation).options(joinedload(AIRecommendation.product))
    if product_id is not None:
        stmt = stmt.where(AIRecommendation.product_id == product_id)
    if status:
        stmt = stmt.where(AIRecommendation.status == status)
    if risk_level:
        stmt = stmt.where(AIRecommendation.risk_level == risk_level)
    stmt = stmt.order_by(AIRecommendation.created_at.desc(), AIRecommendation.id.desc())
    return db.scalars(stmt.offset(skip).limit(limit)).all()


def get_recommendation(db: Session, recommendation_id: int) -> AIRecommendation | None:
    stmt = (
        select(AIRecommendation)
        .options(joinedload(AIRecommendation.product))
        .where(AIRecommendation.id == recommendation_id)
    )
    return db.scalars(stmt).one_or_none()
