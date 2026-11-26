from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import AIRecommendation, PurchaseOrder, PurchaseOrderItem


def next_id(db: Session) -> int:
    """Reserve the next id so po_number can be derived from it in the same INSERT."""
    return db.scalar(select(func.nextval("purchase_orders_id_seq")))


def _with_details():
    return (
        joinedload(PurchaseOrder.supplier),
        selectinload(PurchaseOrder.items).joinedload(PurchaseOrderItem.product),
    )


def list_orders(
    db: Session,
    *,
    status: str | None = None,
    supplier_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> Sequence[PurchaseOrder]:
    stmt = select(PurchaseOrder).options(*_with_details())
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    if supplier_id is not None:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    stmt = stmt.order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc())
    return db.scalars(stmt.offset(skip).limit(limit)).unique().all()


def get_order(db: Session, order_id: int) -> PurchaseOrder | None:
    stmt = select(PurchaseOrder).options(*_with_details()).where(PurchaseOrder.id == order_id)
    return db.scalars(stmt).unique().one_or_none()


def lock_recommendation(db: Session, recommendation_id: int) -> AIRecommendation | None:
    """Row lock: two requests must not turn the same recommendation into two orders."""
    return db.get(AIRecommendation, recommendation_id, with_for_update=True, populate_existing=True)
