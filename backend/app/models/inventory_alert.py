import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.ai_recommendation import AIRecommendation
    from app.models.product import Product


class AlertType(str, enum.Enum):
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    OVERSTOCKED = "OVERSTOCKED"


class AlertSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


def _in(column: str, values: type[enum.Enum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


class InventoryAlert(Base):
    __tablename__ = "inventory_alerts"
    __table_args__ = (
        CheckConstraint(_in("alert_type", AlertType), name="alert_type_valid"),
        CheckConstraint(_in("severity", AlertSeverity), name="severity_valid"),
        CheckConstraint(_in("status", AlertStatus), name="status_valid"),
        # resolved_at is set exactly when the alert is RESOLVED.
        CheckConstraint(
            "(status = 'RESOLVED') = (resolved_at IS NOT NULL)", name="resolved_at_matches_status"
        ),
        # Business rule: at most one unresolved alert per product and stock condition.
        # Enforced in the database so concurrent monitoring runs cannot create duplicates.
        Index(
            "uq_inventory_alerts_product_id_alert_type_unresolved",
            "product_id",
            "alert_type",
            unique=True,
            postgresql_where=text("status <> 'RESOLVED'"),
        ),
        Index("ix_inventory_alerts_status_created_at", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    alert_type: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=AlertStatus.OPEN.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    product: Mapped["Product"] = relationship(back_populates="alerts")
    recommendations: Mapped[list["AIRecommendation"]] = relationship(
        back_populates="alert", passive_deletes="all"
    )

    def __repr__(self) -> str:
        return (
            f"<InventoryAlert id={self.id} product_id={self.product_id} "
            f"{self.alert_type} {self.severity} {self.status}>"
        )
