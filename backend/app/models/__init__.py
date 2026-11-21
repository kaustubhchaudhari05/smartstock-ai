"""ORM models. Import every model here so Alembic autogenerate and relationships see them."""

from app.models.product import Product
from app.models.supplier import Supplier

__all__ = ["Product", "Supplier"]
