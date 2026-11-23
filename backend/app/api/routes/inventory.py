from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession
from app.models import TransactionType
from app.schemas.inventory import (
    InventoryOverview,
    InventoryTransactionCreate,
    InventoryTransactionRead,
    ProductInventoryDetail,
    StockMovementResult,
)
from app.services import inventory_service

router = APIRouter(prefix="/inventory", tags=["inventory"])

# The /transactions routes are declared before /{product_id} so "transactions"
# is never parsed as a product id.


@router.get("/transactions", response_model=list[InventoryTransactionRead])
def list_transactions(
    db: DbSession,
    product_id: int | None = None,
    transaction_type: TransactionType | None = None,
    date_from: Annotated[datetime | None, Query(description="Inclusive, ISO 8601")] = None,
    date_to: Annotated[datetime | None, Query(description="Exclusive, ISO 8601")] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    return inventory_service.list_transactions(
        db,
        product_id=product_id,
        transaction_type=transaction_type.value if transaction_type else None,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/transactions", response_model=StockMovementResult, status_code=status.HTTP_201_CREATED
)
def record_transaction(data: InventoryTransactionCreate, db: DbSession):
    return inventory_service.record_movement(db, data)


@router.get("", response_model=InventoryOverview)
def inventory_overview(
    db: DbSession,
    category: Annotated[str | None, Query(max_length=100)] = None,
    include_inactive: bool = False,
):
    return inventory_service.get_overview(
        db, category=category.strip() if category else None, include_inactive=include_inactive
    )


@router.get("/{product_id}", response_model=ProductInventoryDetail)
def product_inventory(product_id: int, db: DbSession):
    return inventory_service.get_product_inventory(db, product_id)
