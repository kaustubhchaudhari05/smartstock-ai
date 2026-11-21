from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.product import Product


class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint("quantity_sold > 0", name="quantity_sold_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        # Sales analytics query by product over a date window (7/30-day metrics).
        Index("ix_sales_product_id_sale_date", "product_id", "sale_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity_sold: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    sale_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reference: Mapped[str | None] = mapped_column(String(100))

    product: Mapped["Product"] = relationship(back_populates="sales")

    def __repr__(self) -> str:
        return f"<Sale id={self.id} product_id={self.product_id} qty={self.quantity_sold}>"
