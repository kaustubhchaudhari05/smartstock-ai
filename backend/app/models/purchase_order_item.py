from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.purchase_order import PurchaseOrder


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        # Deterministic line total, guaranteed by the database.
        CheckConstraint("total_price = quantity * unit_price", name="total_price_matches"),
        # One line per product per order; change the quantity instead of adding a second line.
        UniqueConstraint("purchase_order_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(back_populates="purchase_order_items")

    def __repr__(self) -> str:
        return (
            f"<PurchaseOrderItem id={self.id} po={self.purchase_order_id} product={self.product_id} "
            f"{self.quantity} x {self.unit_price} = {self.total_price}>"
        )
