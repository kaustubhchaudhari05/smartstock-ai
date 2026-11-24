from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import AlertStatus, InventoryAlert, Product


def list_alerts(
    db: Session,
    *,
    status: str | None = None,
    unresolved_only: bool = False,
    alert_type: str | None = None,
    severity: str | None = None,
    product_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> Sequence[InventoryAlert]:
    stmt = select(InventoryAlert).options(joinedload(InventoryAlert.product))
    if status:
        stmt = stmt.where(InventoryAlert.status == status)
    if unresolved_only:
        stmt = stmt.where(InventoryAlert.status != AlertStatus.RESOLVED.value)
    if alert_type:
        stmt = stmt.where(InventoryAlert.alert_type == alert_type)
    if severity:
        stmt = stmt.where(InventoryAlert.severity == severity)
    if product_id is not None:
        stmt = stmt.where(InventoryAlert.product_id == product_id)
    stmt = stmt.order_by(InventoryAlert.created_at.desc(), InventoryAlert.id.desc())
    return db.scalars(stmt.offset(skip).limit(limit)).all()


def get_alert(db: Session, alert_id: int) -> InventoryAlert | None:
    return db.get(InventoryAlert, alert_id, options=[joinedload(InventoryAlert.product)])


def lock_alert(db: Session, alert_id: int) -> InventoryAlert | None:
    """Load an alert with a row lock on the alert only (the product row is not locked,
    so acknowledging an alert never blocks stock movements)."""
    return db.get(InventoryAlert, alert_id, with_for_update=True, populate_existing=True)


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
