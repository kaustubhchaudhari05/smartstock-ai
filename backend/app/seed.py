"""Load sample data from sample_data/*.csv into the database.

Usage (from backend/):
    python -m app.seed            # load into an empty database
    python -m app.seed --reset    # wipe all application tables first (development only)

Sales dates are shifted so the most recent sale falls on yesterday, keeping the
7/30-day analytics windows meaningful no matter when the seed is run.
Each product with stock also gets an opening-balance STOCK_IN transaction so the
inventory audit trail matches current_stock.
"""

import argparse
import csv
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import Base, SessionLocal
from app.models import InventoryTransaction, Product, Sale, Supplier, TransactionType

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "sample_data"


def _bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes"}


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def reset(db: Session) -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


def seed(db: Session, data_dir: Path) -> dict[str, int]:
    suppliers_csv = _read(data_dir / "suppliers.csv")
    products_csv = _read(data_dir / "products.csv")
    sales_csv = _read(data_dir / "sales.csv")

    suppliers: dict[str, Supplier] = {}
    for row in suppliers_csv:
        supplier = Supplier(
            name=row["name"],
            email=row["email"],
            phone=row["phone"] or None,
            address=row["address"] or None,
            lead_time_days=int(row["lead_time_days"]),
            is_active=_bool(row["is_active"]),
        )
        suppliers[supplier.name] = supplier
    db.add_all(suppliers.values())

    products: dict[str, Product] = {}
    for row in products_csv:
        supplier_name = row["supplier_name"]
        if supplier_name and supplier_name not in suppliers:
            raise ValueError(f"Product {row['sku']}: unknown supplier {supplier_name!r}")
        product = Product(
            sku=row["sku"],
            name=row["name"],
            category=row["category"],
            description=row["description"] or None,
            current_stock=int(row["current_stock"]),
            reorder_point=int(row["reorder_point"]),
            minimum_stock=int(row["minimum_stock"]),
            reorder_quantity=int(row["reorder_quantity"]),
            unit_cost=Decimal(row["unit_cost"]),
            supplier=suppliers.get(supplier_name),
            is_active=_bool(row["is_active"]),
        )
        products[product.sku] = product
    db.add_all(products.values())

    opening = [
        InventoryTransaction(
            product=p,
            transaction_type=TransactionType.STOCK_IN.value,
            quantity=p.current_stock,
            reference="OPENING-BALANCE",
            notes="Opening stock loaded from sample data",
        )
        for p in products.values()
        if p.current_stock > 0
    ]
    db.add_all(opening)

    sales: list[Sale] = []
    if sales_csv:
        parsed = [(row, datetime.fromisoformat(row["sale_date"])) for row in sales_csv]
        latest = max(ts for _, ts in parsed).date()
        shift = (date.today() - timedelta(days=1)) - latest
        for row, ts in parsed:
            if row["sku"] not in products:
                raise ValueError(f"Sale {row['reference']}: unknown SKU {row['sku']!r}")
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            sales.append(
                Sale(
                    product=products[row["sku"]],
                    quantity_sold=int(row["quantity_sold"]),
                    unit_price=Decimal(row["unit_price"]),
                    sale_date=ts + shift,
                    reference=row["reference"] or None,
                )
            )
        db.add_all(sales)

    db.flush()
    return {
        "suppliers": len(suppliers),
        "products": len(products),
        "inventory_transactions": len(opening),
        "sales": len(sales),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Load SmartStock AI sample data.")
    parser.add_argument("--reset", action="store_true", help="wipe all application tables first")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()

    if args.reset and get_settings().environment.lower() == "production":
        print("Refusing to --reset in a production environment.", file=sys.stderr)
        return 1
    if not args.data_dir.is_dir():
        print(f"Data directory not found: {args.data_dir}", file=sys.stderr)
        return 1

    with SessionLocal() as db, db.begin():
        if args.reset:
            reset(db)
        elif db.scalar(select(func.count()).select_from(Product)):
            print("Database already has products; run with --reset to reload.", file=sys.stderr)
            return 1
        counts = seed(db, args.data_dir)

    print("Seeded: " + ", ".join(f"{n} {name}" for name, n in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
