"""ORM models. Import every model here so Alembic autogenerate and relationships see them."""

from app.models.ai_recommendation import AIRecommendation, RecommendationStatus, RiskLevel
from app.models.inventory_alert import AlertSeverity, AlertStatus, AlertType, InventoryAlert
from app.models.inventory_transaction import InventoryTransaction, TransactionType
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder, PurchaseOrderStatus
from app.models.purchase_order_item import PurchaseOrderItem
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
    "PurchaseOrder",
    "PurchaseOrderItem",
    "PurchaseOrderStatus",
    "RecommendationStatus",
    "RiskLevel",
    "Sale",
    "Supplier",
    "TransactionType",
]
