import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.inventory_alert import InventoryAlert
    from app.models.product import Product


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Urgency(str, enum.Enum):
    IMMEDIATE = "IMMEDIATE"  # order today
    SOON = "SOON"  # order within the next few days
    ROUTINE = "ROUTINE"  # include in the next regular order
    NONE = "NONE"  # no order needed now


class RecommendationStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


def _in(column: str, values: type[enum.Enum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


class AIRecommendation(Base):
    """A validated LLM recommendation. Decision support only; never modifies inventory.

    risk_level is decided by backend rules; urgency, recommendation, suggested_quantity and
    reasoning come from the LLM (validated). `context` is the exact data the LLM was given.
    """

    __tablename__ = "ai_recommendations"
    __table_args__ = (
        CheckConstraint(_in("risk_level", RiskLevel), name="risk_level_valid"),
        CheckConstraint(_in("status", RecommendationStatus), name="status_valid"),
        CheckConstraint(_in("urgency", Urgency), name="urgency_valid"),
        # 0 is allowed ("no order needed now").
        CheckConstraint("suggested_quantity >= 0", name="suggested_quantity_non_negative"),
        CheckConstraint(
            "(prompt_tokens IS NULL OR prompt_tokens >= 0) "
            "AND (completion_tokens IS NULL OR completion_tokens >= 0)",
            name="token_counts_non_negative",
        ),
        Index("ix_ai_recommendations_status_created_at", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    alert_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_alerts.id", ondelete="RESTRICT"), index=True
    )
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    urgency: Mapped[str] = mapped_column(String(20), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)  # one point per line
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=RecommendationStatus.PENDING_REVIEW.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    product: Mapped["Product"] = relationship(back_populates="recommendations")
    alert: Mapped["InventoryAlert | None"] = relationship(back_populates="recommendations")

    def __repr__(self) -> str:
        return (
            f"<AIRecommendation id={self.id} product_id={self.product_id} "
            f"{self.risk_level} qty={self.suggested_quantity} {self.status}>"
        )
