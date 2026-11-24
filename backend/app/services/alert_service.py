"""Inventory monitoring: turn stock status into alerts.

For each product the desired state is derived from its current stock:
    OUT_OF_STOCK -> one unresolved OUT_OF_STOCK alert (CRITICAL)
    LOW_STOCK    -> one unresolved LOW_STOCK alert (HIGH at/below minimum_stock, else MEDIUM)
    HEALTHY      -> no unresolved alerts
    inactive     -> no unresolved alerts

check_product() moves a product's alerts to that state: it creates missing alerts,
updates severity/message of existing ones, and resolves alerts whose condition no
longer applies. Duplicate unresolved alerts are prevented by the database (partial
unique index); a concurrent insert that loses the race is treated as "already exists".
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AlertSeverity, AlertStatus, AlertType, InventoryAlert, Product
from app.repositories import alert_repository
from app.schemas.alert import AlertDetail, AlertProductStock, AlertRead
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.services.reorder_service import InventoryStatus, classify_stock

UNIQUE_UNRESOLVED_INDEX = "uq_inventory_alerts_product_id_alert_type_unresolved"


@dataclass
class ProductCheck:
    product_id: int
    status: InventoryStatus
    created: list[InventoryAlert] = field(default_factory=list)
    updated: list[InventoryAlert] = field(default_factory=list)
    resolved: list[InventoryAlert] = field(default_factory=list)


@dataclass
class MonitoringSummary:
    products_checked: int = 0
    alerts_created: int = 0
    alerts_updated: int = 0
    alerts_resolved: int = 0


def desired_alert(product: Product) -> tuple[AlertType, AlertSeverity, str] | None:
    """The alert a product should have right now, or None. Pure and deterministic."""
    if not product.is_active:
        return None
    status = classify_stock(product.current_stock, product.reorder_point)
    label = f"{product.name} ({product.sku})"
    if status == InventoryStatus.OUT_OF_STOCK:
        return (
            AlertType.OUT_OF_STOCK,
            AlertSeverity.CRITICAL,
            f"{label} is out of stock (reorder point {product.reorder_point}).",
        )
    if status == InventoryStatus.LOW_STOCK:
        below_minimum = product.current_stock <= product.minimum_stock
        severity = AlertSeverity.HIGH if below_minimum else AlertSeverity.MEDIUM
        detail = (
            f"at or below minimum stock {product.minimum_stock}"
            if below_minimum
            else f"at or below reorder point {product.reorder_point}"
        )
        return (
            AlertType.LOW_STOCK,
            severity,
            f"{label} is low on stock: {product.current_stock} units, {detail}.",
        )
    return None


def _resolve(alert: InventoryAlert, now: datetime) -> None:
    alert.status = AlertStatus.RESOLVED.value
    alert.resolved_at = now


def check_product(db: Session, product: Product) -> ProductCheck:
    """Bring one product's alerts in line with its stock. Flushes but does not commit."""
    now = datetime.now(timezone.utc)
    result = ProductCheck(
        product_id=product.id, status=classify_stock(product.current_stock, product.reorder_point)
    )
    desired = desired_alert(product)
    existing = alert_repository.unresolved_for_product(db, product.id)

    keep: InventoryAlert | None = None
    for alert in existing:
        if desired is not None and alert.alert_type == desired[0].value and keep is None:
            keep = alert
        else:
            _resolve(alert, now)
            result.resolved.append(alert)

    if desired is not None:
        alert_type, severity, message = desired
        if keep is not None:
            if keep.severity != severity.value or keep.message != message:
                keep.severity, keep.message = severity.value, message
                result.updated.append(keep)
        else:
            alert = InventoryAlert(
                product_id=product.id,
                alert_type=alert_type.value,
                severity=severity.value,
                message=message,
            )
            try:
                with db.begin_nested():
                    db.add(alert)
                result.created.append(alert)
            except IntegrityError as exc:
                if UNIQUE_UNRESOLVED_INDEX not in str(exc.orig):
                    raise
                # Another transaction created the same unresolved alert concurrently.
    db.flush()
    return result


def run_inventory_check(db: Session) -> MonitoringSummary:
    """Check every product and commit. Used by `python -m app.monitor` (and Celery in Phase 8)."""
    summary = MonitoringSummary()
    try:
        for product in alert_repository.all_products(db):
            check = check_product(db, product)
            summary.products_checked += 1
            summary.alerts_created += len(check.created)
            summary.alerts_updated += len(check.updated)
            summary.alerts_resolved += len(check.resolved)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return summary


# ---------- read / acknowledge (alerts API) ----------

# Users can only acknowledge (OPEN -> ACKNOWLEDGED) or un-acknowledge (ACKNOWLEDGED -> OPEN).
# Resolving is automatic (stock recovery or deactivation); resolving by hand while the
# condition persists would just re-raise the alert on the next check.


def to_alert_read(alert: InventoryAlert) -> AlertRead:
    return AlertRead(
        id=alert.id,
        product_id=alert.product_id,
        product_sku=alert.product.sku,
        product_name=alert.product.name,
        alert_type=alert.alert_type,
        severity=alert.severity,
        message=alert.message,
        status=alert.status,
        created_at=alert.created_at,
        resolved_at=alert.resolved_at,
    )


def to_alert_detail(alert: InventoryAlert) -> AlertDetail:
    p = alert.product
    return AlertDetail(
        **to_alert_read(alert).model_dump(),
        product=AlertProductStock(
            current_stock=p.current_stock,
            reorder_point=p.reorder_point,
            minimum_stock=p.minimum_stock,
            reorder_quantity=p.reorder_quantity,
            inventory_status=classify_stock(p.current_stock, p.reorder_point),
            is_active=p.is_active,
        ),
    )


def list_alerts(db: Session, **filters) -> list[AlertRead]:
    return [to_alert_read(a) for a in alert_repository.list_alerts(db, **filters)]


def get_alert(db: Session, alert_id: int) -> AlertDetail:
    alert = alert_repository.get_alert(db, alert_id)
    if alert is None:
        raise NotFoundError(f"Alert {alert_id} not found")
    return to_alert_detail(alert)


def update_alert_status(db: Session, alert_id: int, new_status: AlertStatus) -> AlertDetail:
    try:
        # Row lock: monitoring may be resolving the same alert concurrently.
        alert = alert_repository.lock_alert(db, alert_id)
        if alert is None:
            raise NotFoundError(f"Alert {alert_id} not found")
        current, target = alert.status, new_status.value
        if current != target:
            if current == AlertStatus.RESOLVED.value:
                raise ConflictError(f"Alert {alert_id} is already resolved")
            if target == AlertStatus.RESOLVED.value:
                raise BusinessRuleError(
                    "Alerts resolve automatically when stock recovers or the product is "
                    "deactivated; acknowledge the alert instead"
                )
            alert.status = target  # OPEN <-> ACKNOWLEDGED
            db.commit()
        else:
            db.rollback()  # release the row lock; nothing changed
    except Exception:
        db.rollback()
        raise
    return get_alert(db, alert_id)
