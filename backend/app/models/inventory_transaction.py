import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.product import Product


class TransactionType(str, enum.Enum):
    STOCK_IN = "STOCK_IN"
    STOCK_OUT = "STOCK_OUT"
    ADJUSTMENT = "ADJUSTMENT"
    RETURN = "RETURN"


_TYPE_VALUES = ", ".join(f"'{t.value}'" for t in TransactionType)


class InventoryTransaction(Base):
    """Audit trail of every stock movement. Rows are append-only."""

    __tablename__ = "inventory_transactions"
    __table_args__ = (
        CheckConstraint(f"transaction_type IN ({_TYPE_VALUES})", name="transaction_type_valid"),
        # STOCK_IN / STOCK_OUT / RETURN carry a positive quantity (direction comes from the type).
        # ADJUSTMENT is signed (+ to add, - to remove). Zero-quantity movements are meaningless.
        CheckConstraint(
            "quantity <> 0 AND (transaction_type = 'ADJUSTMENT' OR quantity > 0)",
            name="quantity_valid",
        ),
        Index("ix_inventory_transactions_product_id_created_at", "product_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    product: Mapped["Product"] = relationship(back_populates="inventory_transactions")

    def __repr__(self) -> str:
        return (
            f"<InventoryTransaction id={self.id} product_id={self.product_id} "
            f"{self.transaction_type} {self.quantity}>"
        )
