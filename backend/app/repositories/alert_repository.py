from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AlertStatus, InventoryAlert, Product


def unresolved_for_product(db: Session, product_id: int) -> Sequence[InventoryAlert]:
    stmt = (
        select(InventoryAlert)
        .where(
            InventoryAlert.product_id == product_id,
            InventoryAlert.status != AlertStatus.RESOLVED.value,
        )
        .order_by(InventoryAlert.id)
    )
    return db.scalars(stmt).all()


def all_products(db: Session) -> Sequence[Product]:
    return db.scalars(select(Product).order_by(Product.id)).all()
