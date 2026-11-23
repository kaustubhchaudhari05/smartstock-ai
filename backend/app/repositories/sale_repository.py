from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Sale


def list_sales(
    db: Session,
    *,
    product_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    skip: int = 0,
    limit: int = 100,
) -> Sequence[Sale]:
    stmt = select(Sale).options(joinedload(Sale.product))
    if product_id is not None:
        stmt = stmt.where(Sale.product_id == product_id)
    if date_from:
        stmt = stmt.where(Sale.sale_date >= date_from)
    if date_to:
        stmt = stmt.where(Sale.sale_date < date_to)
    stmt = stmt.order_by(Sale.sale_date.desc(), Sale.id.desc()).offset(skip).limit(limit)
    return db.scalars(stmt).all()
