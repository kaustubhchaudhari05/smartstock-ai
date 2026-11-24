"""Numeric limits shared by request validation and business rules."""

# Stock quantities are PostgreSQL INTEGER columns.
MAX_STOCK = 2_147_483_647

# Largest single stock movement or sale; anything larger is almost certainly a typo.
MAX_MOVEMENT_QUANTITY = 1_000_000
