"""Sales business rules. A sale and its STOCK_OUT movement are recorded atomically."""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.models import Sale, TransactionType
from app.repositories import sale_repository
from app.schemas.sale import SaleCreate, SaleRead, SaleRecorded
from app.services import inventory_service

CENT = Decimal("0.01")


def to_sale_read(sale: Sale) -> SaleRead:
    return SaleRead(
        id=sale.id,
        product_id=sale.product_id,
        product_sku=sale.product.sku,
        product_name=sale.product.name,
        quantity_sold=sale.quantity_sold,
        unit_price=sale.unit_price,
        total_amount=(sale.quantity_sold * sale.unit_price).quantize(CENT, rounding=ROUND_HALF_UP),
        sale_date=sale.sale_date,
        reference=sale.reference,
    )


def list_sales(db: Session, **filters) -> list[SaleRead]:
    return [to_sale_read(s) for s in sale_repository.list_sales(db, **filters)]


def record_sale(db: Session, data: SaleCreate) -> SaleRecorded:
    try:
        # Locks the product row and rejects the sale if stock is insufficient or the
        # product is inactive, before anything is written.
        txn, previous = inventory_service.apply_movement(
            db,
            product_id=data.product_id,
            transaction_type=TransactionType.STOCK_OUT,
            quantity=data.quantity_sold,
            reference=data.reference,
        )
        sale = Sale(
            product_id=data.product_id,
            quantity_sold=data.quantity_sold,
            unit_price=data.unit_price,
            reference=data.reference,
        )
        if data.sale_date is not None:
            sale.sale_date = data.sale_date
        db.add(sale)
        db.flush()
        txn.notes = f"Sale #{sale.id}"
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(sale)
    return SaleRecorded(
        sale=to_sale_read(sale),
        inventory_transaction_id=txn.id,
        previous_stock=previous,
        current_stock=txn.product.current_stock,
    )
