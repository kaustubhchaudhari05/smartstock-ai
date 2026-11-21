from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.ai_recommendation import AIRecommendation
    from app.models.inventory_alert import InventoryAlert
    from app.models.inventory_transaction import InventoryTransaction
    from app.models.purchase_order_item import PurchaseOrderItem
    from app.models.sale import Sale
    from app.models.supplier import Supplier


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        # Business rule: inventory quantities and thresholds can never be negative.
        CheckConstraint("current_stock >= 0", name="current_stock_non_negative"),
        CheckConstraint("reorder_point >= 0", name="reorder_point_non_negative"),
        CheckConstraint("minimum_stock >= 0", name="minimum_stock_non_negative"),
        CheckConstraint("reorder_quantity >= 0", name="reorder_quantity_non_negative"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)

    current_stock: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    reorder_point: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_stock: Mapped[int] = mapped_column(Integer, nullable=False)
    reorder_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    supplier: Mapped["Supplier | None"] = relationship(back_populates="products")
    # passive_deletes="all": history rows are never nulled/removed by the ORM; the
    # database's ON DELETE RESTRICT blocks deleting a product that has history.
    inventory_transactions: Mapped[list["InventoryTransaction"]] = relationship(
        back_populates="product", passive_deletes="all"
    )
    sales: Mapped[list["Sale"]] = relationship(back_populates="product", passive_deletes="all")
    alerts: Mapped[list["InventoryAlert"]] = relationship(
        back_populates="product", passive_deletes="all"
    )
    recommendations: Mapped[list["AIRecommendation"]] = relationship(
        back_populates="product", passive_deletes="all"
    )
    purchase_order_items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="product", passive_deletes="all"
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} sku={self.sku!r} stock={self.current_stock}>"
