"""Product business rules. All writes happen in a single database transaction."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import InventoryTransaction, Product, Supplier, TransactionType
from app.repositories import product_repository
from app.schemas.product import ProductCreate, ProductUpdate
from app.services import alert_service
from app.services.exceptions import BusinessRuleError, ConflictError, NotFoundError

list_products = product_repository.list_products


def get_product(db: Session, product_id: int) -> Product:
    product = product_repository.get_product(db, product_id)
    if product is None:
        raise NotFoundError(f"Product {product_id} not found")
    return product


def _validate_supplier(db: Session, supplier_id: int | None) -> None:
    if supplier_id is None:
        return
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise BusinessRuleError(f"Supplier {supplier_id} does not exist")
    if not supplier.is_active:
        raise BusinessRuleError(f"Supplier {supplier_id} is inactive")


def _validate_thresholds(minimum_stock: int, reorder_point: int) -> None:
    if minimum_stock > reorder_point:
        raise BusinessRuleError(
            f"minimum_stock ({minimum_stock}) cannot exceed reorder_point ({reorder_point})"
        )


def _ensure_sku_free(db: Session, sku: str, exclude_id: int | None = None) -> None:
    existing = product_repository.get_by_sku(db, sku)
    if existing is not None and existing.id != exclude_id:
        raise ConflictError(f"SKU {sku} already exists")


def _save(db: Session, product: Product) -> None:
    """Write the product, bring its stock alerts in line (thresholds, activation, name and
    opening stock all affect them) and commit, all in one transaction."""
    try:
        db.flush()
        alert_service.check_product(db, product)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Unique SKU can still race between the check and the insert.
        if "uq_products_sku" in str(exc.orig):
            raise ConflictError(f"SKU {product.sku} already exists") from exc
        raise
    except Exception:
        db.rollback()
        raise


def create_product(db: Session, data: ProductCreate) -> Product:
    _validate_supplier(db, data.supplier_id)
    _validate_thresholds(data.minimum_stock, data.reorder_point)
    _ensure_sku_free(db, data.sku)

    product = Product(**data.model_dump())
    db.add(product)
    if product.current_stock > 0:
        # Audit trail: opening stock is a recorded stock movement.
        db.add(
            InventoryTransaction(
                product=product,
                transaction_type=TransactionType.STOCK_IN.value,
                quantity=product.current_stock,
                reference="OPENING-BALANCE",
                notes="Opening stock recorded at product creation",
            )
        )
    _save(db, product)
    return get_product(db, product.id)


def update_product(db: Session, product_id: int, data: ProductUpdate) -> Product:
    product = get_product(db, product_id)
    changes = data.model_dump(exclude_unset=True)

    if "supplier_id" in changes and changes["supplier_id"] != product.supplier_id:
        _validate_supplier(db, changes["supplier_id"])
    _validate_thresholds(
        changes.get("minimum_stock", product.minimum_stock),
        changes.get("reorder_point", product.reorder_point),
    )
    if "sku" in changes and changes["sku"] != product.sku:
        _ensure_sku_free(db, changes["sku"], exclude_id=product.id)

    for field, value in changes.items():
        setattr(product, field, value)
    _save(db, product)
    return get_product(db, product_id)


def deactivate_product(db: Session, product_id: int) -> Product:
    """Soft delete: products keep their sales and stock history, so they are never removed.
    Open alerts are resolved, since inactive products are not monitored."""
    product = get_product(db, product_id)
    if product.is_active:
        product.is_active = False
        _save(db, product)
    return get_product(db, product_id)

