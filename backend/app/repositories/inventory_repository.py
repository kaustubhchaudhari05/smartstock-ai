from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from app.models import InventoryTransaction, Product


def _last_movement_subquery():
    return (
        select(
            InventoryTransaction.product_id,
            func.max(InventoryTransaction.created_at).label("last_stock_update"),
        )
        .group_by(InventoryTransaction.product_id)
        .subquery()
    )


def list_stock(
    db: Session, *, category: str | None = None, include_inactive: bool = False
) -> Sequence[tuple[Product, datetime | None]]:
    last = _last_movement_subquery()
    stmt = select(Product, last.c.last_stock_update).outerjoin(last, last.c.product_id == Product.id)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    if category:
        stmt = stmt.where(func.lower(Product.category) == category.lower())
    return db.execute(stmt.order_by(Product.sku)).tuples().all()


def get_stock(db: Session, product_id: int) -> tuple[Product, datetime | None] | None:
    last = _last_movement_subquery()
    stmt = (
        select(Product, last.c.last_stock_update)
        .outerjoin(last, last.c.product_id == Product.id)
        .where(Product.id == product_id)
    )
    return db.execute(stmt).tuples().first()


def lock_product(db: Session, product_id: int) -> Product | None:
    """Load a product with a row lock (SELECT ... FOR UPDATE) for the rest of the transaction."""
    return db.get(Product, product_id, with_for_update=True, populate_existing=True)


def _transactions_query() -> Select:
    return select(InventoryTransaction).options(joinedload(InventoryTransaction.product))


def list_transactions(
    db: Session,
    *,
    product_id: int | None = None,
    transaction_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    skip: int = 0,
    limit: int = 100,
) -> Sequence[InventoryTransaction]:
    stmt = _transactions_query()
    if product_id is not None:
        stmt = stmt.where(InventoryTransaction.product_id == product_id)
    if transaction_type:
        stmt = stmt.where(InventoryTransaction.transaction_type == transaction_type)
    if date_from:
        stmt = stmt.where(InventoryTransaction.created_at >= date_from)
    if date_to:
        stmt = stmt.where(InventoryTransaction.created_at < date_to)
    stmt = stmt.order_by(InventoryTransaction.created_at.desc(), InventoryTransaction.id.desc())
    return db.scalars(stmt.offset(skip).limit(limit)).all()
