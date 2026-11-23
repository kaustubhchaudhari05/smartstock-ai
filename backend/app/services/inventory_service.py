"""Inventory business rules: stock movements, stock value and the inventory overview.

Every stock change goes through record_movement(), which locks the product row,
validates the new level, writes the audit-trail row and updates current_stock in
one database transaction.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.models import InventoryTransaction, Product, TransactionType
from app.repositories import inventory_repository
from app.schemas.inventory import (
    InventoryItem,
    InventoryOverview,
    InventorySummary,
    InventoryTransactionCreate,
    InventoryTransactionRead,
    ProductInventoryDetail,
    StockMovementResult,
)
from app.services.exceptions import BusinessRuleError, NotFoundError

CENT = Decimal("0.01")
RECENT_TRANSACTIONS = 20


def stock_change(transaction_type: str, quantity: int) -> int:
    """Signed effect of a movement on current_stock."""
    if transaction_type == TransactionType.STOCK_OUT.value:
        return -quantity
    # STOCK_IN and RETURN add stock; ADJUSTMENT is already signed.
    return quantity


def stock_value(product: Product) -> Decimal:
    return (product.current_stock * product.unit_cost).quantize(CENT, rounding=ROUND_HALF_UP)


def to_transaction_read(txn: InventoryTransaction) -> InventoryTransactionRead:
    return InventoryTransactionRead(
        id=txn.id,
        product_id=txn.product_id,
        product_sku=txn.product.sku,
        product_name=txn.product.name,
        transaction_type=txn.transaction_type,
        quantity=txn.quantity,
        stock_change=stock_change(txn.transaction_type, txn.quantity),
        reference=txn.reference,
        notes=txn.notes,
        created_at=txn.created_at,
    )


def _to_item(product: Product, last_update: datetime | None) -> dict:
    return {
        "product_id": product.id,
        "sku": product.sku,
        "name": product.name,
        "category": product.category,
        "is_active": product.is_active,
        "current_stock": product.current_stock,
        "reorder_point": product.reorder_point,
        "minimum_stock": product.minimum_stock,
        "reorder_quantity": product.reorder_quantity,
        "unit_cost": product.unit_cost,
        "stock_value": stock_value(product),
        "supplier_id": product.supplier_id,
        "last_stock_update": last_update,
    }


def get_overview(
    db: Session, *, category: str | None = None, include_inactive: bool = False
) -> InventoryOverview:
    rows = inventory_repository.list_stock(db, category=category, include_inactive=include_inactive)
    items = [InventoryItem(**_to_item(p, last)) for p, last in rows]
    summary = InventorySummary(
        total_products=len(items),
        total_units=sum(i.current_stock for i in items),
        total_stock_value=sum((i.stock_value for i in items), Decimal("0.00")),
    )
    return InventoryOverview(summary=summary, items=items)


def get_product_inventory(db: Session, product_id: int) -> ProductInventoryDetail:
    row = inventory_repository.get_stock(db, product_id)
    if row is None:
        raise NotFoundError(f"Product {product_id} not found")
    product, last = row
    recent = inventory_repository.list_transactions(db, product_id=product_id, limit=RECENT_TRANSACTIONS)
    return ProductInventoryDetail(
        **_to_item(product, last), recent_transactions=[to_transaction_read(t) for t in recent]
    )


def list_transactions(db: Session, **filters) -> list[InventoryTransactionRead]:
    return [to_transaction_read(t) for t in inventory_repository.list_transactions(db, **filters)]


def apply_movement(
    db: Session,
    *,
    product_id: int,
    transaction_type: TransactionType,
    quantity: int,
    reference: str | None = None,
    notes: str | None = None,
) -> tuple[InventoryTransaction, int]:
    """Lock the product, validate and apply a stock movement. Does not commit.

    Returns the new transaction and the stock level before the movement.
    Callers (this module, the sales service) commit as part of their own unit of work.
    """
    product = inventory_repository.lock_product(db, product_id)
    if product is None:
        raise NotFoundError(f"Product {product_id} not found")
    if not product.is_active:
        raise BusinessRuleError(f"Product {product.sku} is inactive; reactivate it before moving stock")

    previous = product.current_stock
    new_stock = previous + stock_change(transaction_type.value, quantity)
    if new_stock < 0:
        raise BusinessRuleError(
            f"Insufficient stock for {product.sku}: {previous} available, "
            f"movement would leave {new_stock}"
        )

    txn = InventoryTransaction(
        product=product,
        transaction_type=transaction_type.value,
        quantity=quantity,
        reference=reference,
        notes=notes,
    )
    db.add(txn)
    product.current_stock = new_stock
    db.flush()
    return txn, previous


def record_movement(db: Session, data: InventoryTransactionCreate) -> StockMovementResult:
    try:
        txn, previous = apply_movement(
            db,
            product_id=data.product_id,
            transaction_type=data.transaction_type,
            quantity=data.quantity,
            reference=data.reference,
            notes=data.notes,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(txn)
    return StockMovementResult(
        transaction=to_transaction_read(txn),
        previous_stock=previous,
        current_stock=txn.product.current_stock,
    )
