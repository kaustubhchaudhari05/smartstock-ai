from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate
from app.services import product_service

router = APIRouter(prefix="/products", tags=["products"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[ProductRead])
def list_products(
    db: DbSession,
    search: Annotated[str | None, Query(max_length=100, description="Match name or SKU")] = None,
    category: Annotated[str | None, Query(max_length=100)] = None,
    supplier_id: int | None = None,
    include_inactive: bool = False,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    return product_service.list_products(
        db,
        search=search.strip() if search else None,
        category=category.strip() if category else None,
        supplier_id=supplier_id,
        include_inactive=include_inactive,
        skip=skip,
        limit=limit,
    )


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: DbSession):
    return product_service.get_product(db, product_id)


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(data: ProductCreate, db: DbSession):
    return product_service.create_product(db, data)


@router.put("/{product_id}", response_model=ProductRead)
def update_product(product_id: int, data: ProductUpdate, db: DbSession):
    return product_service.update_product(db, product_id, data)


@router.delete("/{product_id}", response_model=ProductRead)
def deactivate_product(product_id: int, db: DbSession):
    return product_service.deactivate_product(db, product_id)
