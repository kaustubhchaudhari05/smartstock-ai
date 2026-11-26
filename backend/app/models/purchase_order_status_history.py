from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.purchase_order import PurchaseOrderStatus

if TYPE_CHECKING:
    from app.models.purchase_order import PurchaseOrder

_STATUSES = ", ".join(repr(s.value) for s in PurchaseOrderStatus)


class PurchaseOrderStatusHistory(Base):
    """Append-only audit trail of purchase order status changes (creation, approval, rejection).

    `changed_by` is the approver name supplied with the decision (null for system actions such
    as creating a draft). Rows are never updated or deleted.
    """

    __tablename__ = "purchase_order_status_history"
    __table_args__ = (
        CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_STATUSES})", name="from_status_valid"
        ),
        CheckConstraint(f"to_status IN ({_STATUSES})", name="to_status_valid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(100))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="status_history")

    def __repr__(self) -> str:
        return (
            f"<PurchaseOrderStatusHistory po={self.purchase_order_id} "
            f"{self.from_status}->{self.to_status} by={self.changed_by}>"
        )
