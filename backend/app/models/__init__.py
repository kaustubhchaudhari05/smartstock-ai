"""ORM models. Import every model here so Alembic autogenerate and relationships see them."""

from app.models.ai_recommendation import AIRecommendation, RecommendationStatus, RiskLevel
from app.models.inventory_alert import AlertSeverity, AlertStatus, AlertType, InventoryAlert
from app.models.inventory_transaction import InventoryTransaction, TransactionType
from app.models.product import Product
from app.models.sale import Sale
from app.models.supplier import Supplier

__all__ = [
    "AIRecommendation",
    "AlertSeverity",
    "AlertStatus",
    "AlertType",
    "InventoryAlert",
    "InventoryTransaction",
    "Product",
    "RecommendationStatus",
    "RiskLevel",
    "Sale",
    "Supplier",
    "TransactionType",
]
