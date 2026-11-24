from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.core.limits import MAX_STOCK

SKU_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"

# SKUs are stored upper-case so "wm-001" and "WM-001" cannot both exist.
Sku = Annotated[
    str, Field(min_length=1, max_length=64, pattern=SKU_PATTERN), AfterValidator(str.upper)
]
Name = Annotated[str, Field(min_length=1, max_length=255)]
Category = Annotated[str, Field(min_length=1, max_length=100)]
Quantity = Annotated[int, Field(ge=0, le=MAX_STOCK)]
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class ProductCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    sku: Sku
    name: Name
    category: Category
    description: str | None = None
    current_stock: Quantity = Field(
        default=0, description="Opening stock; recorded as a STOCK_IN transaction."
    )
    reorder_point: Quantity
    minimum_stock: Quantity
    reorder_quantity: Quantity
    unit_cost: Money
    supplier_id: int | None = None


class ProductUpdate(BaseModel):
    """Partial update. Stock levels are changed through inventory transactions, not here."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    sku: Sku | None = None
    name: Name | None = None
    category: Category | None = None
    description: str | None = None
    reorder_point: Quantity | None = None
    minimum_stock: Quantity | None = None
    reorder_quantity: Quantity | None = None
    unit_cost: Money | None = None
    supplier_id: int | None = None
    is_active: bool | None = None

    @field_validator(
        "sku", "name", "category", "reorder_point", "minimum_stock", "reorder_quantity",
        "unit_cost", "is_active",
    )
    @classmethod
    def not_null(cls, value):
        # Only description and supplier_id may be cleared with an explicit null.
        if value is None:
            raise ValueError("may not be null")
        return value


class SupplierSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    category: str
    description: str | None
    current_stock: int
    reorder_point: int
    minimum_stock: int
    reorder_quantity: int
    unit_cost: Decimal
    supplier_id: int | None
    supplier: SupplierSummary | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
