from datetime import datetime, timezone
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class SaleCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    product_id: int
    quantity_sold: int = Field(gt=0)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    sale_date: AwareDatetime | None = Field(
        default=None, description="Defaults to now. Must include a timezone; cannot be in the future."
    )
    reference: str | None = Field(default=None, max_length=100)

    @field_validator("sale_date")
    @classmethod
    def not_in_future(cls, value: datetime | None) -> datetime | None:
        if value is not None and value > datetime.now(timezone.utc):
            raise ValueError("sale_date cannot be in the future")
        return value


class SaleRead(BaseModel):
    id: int
    product_id: int
    product_sku: str
    product_name: str
    quantity_sold: int
    unit_price: Decimal
    total_amount: Decimal = Field(description="quantity_sold x unit_price, calculated by the backend")
    sale_date: datetime
    reference: str | None


class SaleRecorded(BaseModel):
    sale: SaleRead
    inventory_transaction_id: int
    previous_stock: int
    current_stock: int
