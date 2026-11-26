from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession
from app.models.purchase_order import PurchaseOrderStatus
from app.schemas.purchase_order import PurchaseOrderCreate, PurchaseOrderDetail, PurchaseOrderRead
from app.services import purchase_order_service

router = APIRouter(prefix="/purchase-orders", tags=["purchase orders"])


@router.post("", response_model=PurchaseOrderDetail, status_code=status.HTTP_201_CREATED)
def create_purchase_order(data: PurchaseOrderCreate, db: DbSession):
    """Create a DRAFT purchase order (nothing is sent to the supplier and stock is unchanged).

    From an AI recommendation: `{"recommendation_id": 1}` (optional `quantity`, `unit_price`,
    `supplier_id` overrides); the recommendation becomes ACCEPTED and can be used only once.
    Manual: `{"supplier_id": 1, "items": [{"product_id": 1, "quantity": 100}]}`.
    Totals are calculated by the backend.
    """
    return purchase_order_service.create_draft(db, data)


@router.get("", response_model=list[PurchaseOrderRead])
def list_purchase_orders(
    db: DbSession,
    status: PurchaseOrderStatus | None = None,
    supplier_id: int | None = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    return purchase_order_service.list_orders(
        db, status=status.value if status else None, supplier_id=supplier_id, skip=skip, limit=limit
    )


@router.get("/{order_id}", response_model=PurchaseOrderDetail)
def get_purchase_order(order_id: int, db: DbSession):
    return purchase_order_service.get_order(db, order_id)
