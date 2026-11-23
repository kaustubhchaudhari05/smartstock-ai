"""Supplier business rules."""

from sqlalchemy.orm import Session

from app.models import Supplier
from app.repositories import supplier_repository
from app.schemas.supplier import SupplierCreate, SupplierUpdate
from app.services.exceptions import ConflictError, NotFoundError

list_suppliers = supplier_repository.list_suppliers


def get_supplier(db: Session, supplier_id: int) -> Supplier:
    supplier = supplier_repository.get_supplier(db, supplier_id)
    if supplier is None:
        raise NotFoundError(f"Supplier {supplier_id} not found")
    return supplier


def _ensure_name_free(db: Session, name: str, exclude_id: int | None = None) -> None:
    # Duplicate supplier names would make supplier selection on purchase orders ambiguous.
    existing = supplier_repository.get_by_name(db, name)
    if existing is not None and existing.id != exclude_id:
        raise ConflictError(f"Supplier named {existing.name!r} already exists")


def create_supplier(db: Session, data: SupplierCreate) -> Supplier:
    _ensure_name_free(db, data.name)
    supplier = Supplier(**data.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def update_supplier(db: Session, supplier_id: int, data: SupplierUpdate) -> Supplier:
    supplier = get_supplier(db, supplier_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        _ensure_name_free(db, changes["name"], exclude_id=supplier.id)
    for field, value in changes.items():
        setattr(supplier, field, value)
    db.commit()
    db.refresh(supplier)
    return supplier
