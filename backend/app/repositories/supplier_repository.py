from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Supplier
from app.repositories.utils import escape_like


def list_suppliers(
    db: Session,
    *,
    search: str | None = None,
    include_inactive: bool = False,
    skip: int = 0,
    limit: int = 100,
) -> Sequence[Supplier]:
    stmt = select(Supplier)
    if not include_inactive:
        stmt = stmt.where(Supplier.is_active.is_(True))
    if search:
        stmt = stmt.where(Supplier.name.ilike(f"%{escape_like(search)}%", escape="\\"))
    stmt = stmt.order_by(Supplier.name, Supplier.id).offset(skip).limit(limit)
    return db.scalars(stmt).all()


def get_supplier(db: Session, supplier_id: int) -> Supplier | None:
    return db.get(Supplier, supplier_id)


def get_by_name(db: Session, name: str) -> Supplier | None:
    return db.scalar(select(Supplier).where(func.lower(Supplier.name) == name.lower()))
