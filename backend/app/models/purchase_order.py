import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.purchase_order_item import PurchaseOrderItem
    from app.models.purchase_order_status_history import PurchaseOrderStatusHistory
    from app.models.supplier import Supplier


class PurchaseOrderStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SENT = "SENT"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"


def _sql_list(values) -> str:
    return ", ".join(repr(v.value) for v in values)


S = PurchaseOrderStatus
_ALL = _sql_list(S)
# Statuses that can only be reached through human approval.
_APPROVED_STATES = _sql_list([S.APPROVED, S.SENT, S.RECEIVED])
# CANCELLED may happen before or after approval, so approved_at is optional there.
_MAY_HAVE_APPROVED_AT = _sql_list([S.APPROVED, S.SENT, S.RECEIVED, S.CANCELLED])


class PurchaseOrder(Base):
    """Purchase order header. Totals are calculated by backend logic, never by the LLM."""

    __tablename__ = "purchase_orders"
    __table_args__ = (
        CheckConstraint(f"status IN ({_ALL})", name="status_valid"),
        CheckConstraint("total_amount >= 0", name="total_amount_non_negative"),
        # Approved/sent/received orders must record when they were approved ...
        CheckConstraint(
            f"status NOT IN ({_APPROVED_STATES}) OR approved_at IS NOT NULL",
            name="approved_at_required",
        ),
        # ... and drafts, pending or rejected orders must not carry an approval time.
        CheckConstraint(
            f"approved_at IS NULL OR status IN ({_MAY_HAVE_APPROVED_AT})",
            name="approved_at_only_when_approved",
        ),
        Index("ix_purchase_orders_status_created_at", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    po_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=S.DRAFT.value)
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    supplier: Mapped["Supplier"] = relationship(back_populates="purchase_orders")
    # Line items belong to their order: removed with it (DB: ON DELETE CASCADE).
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PurchaseOrderItem.id",
    )
    # Audit trail: kept with the order (history rows block deleting it).
    status_history: Mapped[list["PurchaseOrderStatusHistory"]] = relationship(
        back_populates="purchase_order",
        passive_deletes="all",
        order_by="PurchaseOrderStatusHistory.id",
    )

    def __repr__(self) -> str:
        return f"<PurchaseOrder id={self.id} {self.po_number} {self.status} total={self.total_amount}>"
