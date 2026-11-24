from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import TransactionType
from app.services.reorder_service import InventoryStatus


class InventoryTransactionCreate(BaseModel):
    """A stock movement. STOCK_IN / STOCK_OUT / RETURN take a positive quantity;
    ADJUSTMENT is signed (+ adds stock, - removes it)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    product_id: int
    transaction_type: TransactionType
    quantity: int = Field(description="Positive, except ADJUSTMENT which may be negative")
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = None

    @model_validator(mode="after")
    def check_quantity(self) -> "InventoryTransactionCreate":
        if self.quantity == 0:
            raise ValueError("quantity cannot be 0")
        if self.transaction_type != TransactionType.ADJUSTMENT and self.quantity < 0:
            raise ValueError(
                f"quantity must be positive for {self.transaction_type.value}; "
                "use ADJUSTMENT for signed corrections"
            )
        return self


class InventoryTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_sku: str
    product_name: str
    transaction_type: str
    quantity: int
    stock_change: int = Field(description="Signed effect on current_stock")
    reference: str | None
    notes: str | None
    created_at: datetime


class StockMovementResult(BaseModel):
    transaction: InventoryTransactionRead
    previous_stock: int
    current_stock: int


class InventoryItem(BaseModel):
    product_id: int
    sku: str
    name: str
    category: str
    is_active: bool
    current_stock: int
    reorder_point: int
    minimum_stock: int
    reorder_quantity: int
    unit_cost: Decimal
    stock_value: Decimal = Field(description="current_stock x unit_cost, calculated by the backend")
    inventory_status: InventoryStatus
    supplier_id: int | None
    last_stock_update: datetime | None = Field(description="Time of the latest stock movement")


class InventorySummary(BaseModel):
    total_products: int
    total_units: int
    total_stock_value: Decimal
    healthy_count: int
    low_stock_count: int
    out_of_stock_count: int
    reorder_needed_count: int = Field(description="Active products at or below their reorder point")
    replenishment_cost: Decimal = Field(
        description="Sum of reorder_quantity x unit_cost for active products that need reordering"
    )


class CategorySummary(InventorySummary):
    category: str


class InventoryOverview(BaseModel):
    summary: InventorySummary
    categories: list[CategorySummary] = Field(description="Same figures per category, sorted by name")
    items: list[InventoryItem]


class ProductInventoryDetail(InventoryItem):
    recent_transactions: list[InventoryTransactionRead]
