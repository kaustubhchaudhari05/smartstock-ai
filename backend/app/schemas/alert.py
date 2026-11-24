from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import AlertStatus
from app.services.reorder_service import InventoryStatus


class AlertRead(BaseModel):
    id: int
    product_id: int
    product_sku: str
    product_name: str
    alert_type: str
    severity: str
    message: str
    status: str
    created_at: datetime
    resolved_at: datetime | None


class AlertProductStock(BaseModel):
    """Live stock context for the alerted product (not a snapshot)."""

    current_stock: int
    reorder_point: int
    minimum_stock: int
    reorder_quantity: int
    inventory_status: InventoryStatus
    is_active: bool


class AlertDetail(AlertRead):
    product: AlertProductStock


class AlertUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AlertStatus
