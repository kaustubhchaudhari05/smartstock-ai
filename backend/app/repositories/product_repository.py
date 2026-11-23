from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Product
from app.repositories.utils import escape_like


def list_products(
    db: Session,
    *,
    search: str | None = None,
    category: str | None = None,
    supplier_id: int | None = None,
    include_inactive: bool = False,
    skip: int = 0,
    limit: int = 100,
) -> Sequence[Product]:
    stmt = select(Product).options(selectinload(Product.supplier))
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    if search:
        pattern = f"%{escape_like(search)}%"
        stmt = stmt.where(
            or_(Product.name.ilike(pattern, escape="\\"), Product.sku.ilike(pattern, escape="\\"))
        )
    if category:
        stmt = stmt.where(func.lower(Product.category) == category.lower())
    if supplier_id is not None:
        stmt = stmt.where(Product.supplier_id == supplier_id)
    stmt = stmt.order_by(Product.sku).offset(skip).limit(limit)
    return db.scalars(stmt).all()


def get_product(db: Session, product_id: int) -> Product | None:
    return db.get(Product, product_id, options=[selectinload(Product.supplier)])


def get_by_sku(db: Session, sku: str) -> Product | None:
    return db.scalar(select(Product).where(Product.sku == sku))
