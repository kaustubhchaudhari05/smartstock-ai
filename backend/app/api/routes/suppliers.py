from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession
from app.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate
from app.services import supplier_service

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("", response_model=list[SupplierRead])
def list_suppliers(
    db: DbSession,
    search: Annotated[str | None, Query(max_length=100, description="Match supplier name")] = None,
    include_inactive: bool = False,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    return supplier_service.list_suppliers(
        db,
        search=search.strip() if search else None,
        include_inactive=include_inactive,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
def create_supplier(data: SupplierCreate, db: DbSession):
    return supplier_service.create_supplier(db, data)


@router.put("/{supplier_id}", response_model=SupplierRead)
def update_supplier(supplier_id: int, data: SupplierUpdate, db: DbSession):
    return supplier_service.update_supplier(db, supplier_id, data)
