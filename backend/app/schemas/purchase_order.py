from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.limits import MAX_MOVEMENT_QUANTITY

OrderQuantity = Annotated[int, Field(ge=1, le=MAX_MOVEMENT_QUANTITY)]
UnitPrice = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Id = Annotated[int, Field(gt=0)]
PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class PurchaseOrderItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: Id
    quantity: OrderQuantity
    unit_price: UnitPrice | None = Field(default=None, description="Defaults to the product's unit_cost")


class PurchaseOrderCreate(BaseModel):
    """Create a DRAFT purchase order, either from an AI recommendation or from explicit lines.

    From a recommendation: `recommendation_id` (+ optional `quantity` / `unit_price` overrides
    and `supplier_id`, which default to the suggested quantity, the product's unit cost and the
    product's supplier). Manual: `supplier_id` + `items`.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"recommendation_id": 1},
                {"supplier_id": 1, "items": [{"product_id": 1, "quantity": 100}]},
            ]
        },
    )

    recommendation_id: Id | None = None
    quantity: OrderQuantity | None = Field(default=None, description="Override (recommendation only)")
    unit_price: UnitPrice | None = Field(default=None, description="Override (recommendation only)")
    supplier_id: Id | None = None
    items: list[PurchaseOrderItemCreate] | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def one_source(self) -> "PurchaseOrderCreate":
        if self.recommendation_id is not None:
            if self.items is not None:
                raise ValueError("Give either recommendation_id or items, not both")
        else:
            if self.items is None:
                raise ValueError("Give recommendation_id, or supplier_id with items")
            if self.supplier_id is None:
                raise ValueError("supplier_id is required with items")
            if self.quantity is not None or self.unit_price is not None:
                raise ValueError("quantity and unit_price overrides apply to recommendation_id only")
        return self


class PurchaseOrderItemRead(BaseModel):
    id: int
    product_id: int
    product_sku: str
    product_name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal = Field(description="quantity x unit_price, computed by the backend")
    recommendation_id: int | None


class PurchaseOrderSupplier(BaseModel):
    id: int
    name: str
    email: str
    phone: str | None
    lead_time_days: int


class PurchaseOrderRead(BaseModel):
    id: int
    po_number: str
    supplier_id: int
    supplier_name: str
    status: str
    total_amount: Decimal = Field(description="Sum of line totals, computed by the backend")
    item_count: int
    created_at: datetime
    approved_at: datetime | None


class PurchaseOrderStatusChange(BaseModel):
    from_status: str | None
    to_status: str
    changed_by: str | None
    comment: str | None
    created_at: datetime


class PurchaseOrderDetail(PurchaseOrderRead):
    supplier: PurchaseOrderSupplier
    items: list[PurchaseOrderItemRead]
    status_history: list[PurchaseOrderStatusChange] = Field(description="Oldest first")


class PurchaseOrderApprove(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"approver": "Priya Shah"}]}
    )

    approver: PersonName
    comment: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None


class PurchaseOrderReject(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"approver": "Priya Shah", "reason": "Quantity too high"}]},
    )

    approver: PersonName
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]


class PurchaseOrderStatusTotal(BaseModel):
    status: str
    order_count: int
    total_amount: Decimal


class PurchaseOrderSummary(BaseModel):
    """Backend-computed counts and values for the dashboard (no arithmetic in the frontend)."""

    awaiting_decision_count: int = Field(description="DRAFT + PENDING_APPROVAL orders")
    awaiting_decision_amount: Decimal
    approved_count: int = Field(description="APPROVED orders (not yet sent)")
    approved_amount: Decimal
    total_orders: int
    by_status: list[PurchaseOrderStatusTotal] = Field(
        description="Every status in workflow order, zero-filled"
    )
