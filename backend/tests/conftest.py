"""Test fixtures.

Tests run against a separate database (<DATABASE_URL db name>_test, created on first use)
so the development data is never touched. Each test runs inside a transaction that is
rolled back afterwards; services may call commit(), which only releases a savepoint.
"""

from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.main import app
from app.models import Product, Supplier

DEV_URL = make_url(get_settings().database_url)
TEST_URL = DEV_URL.set(database=f"{DEV_URL.database}_test")


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    admin = create_engine(DEV_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_URL.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_URL.database}"'))
    admin.dispose()

    test_engine = create_engine(TEST_URL)
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def supplier(db: Session) -> Supplier:
    s = Supplier(name="Acme Peripherals", email="orders@acme.example", lead_time_days=7)
    db.add(s)
    db.flush()
    return s


@pytest.fixture
def inactive_supplier(db: Session) -> Supplier:
    s = Supplier(name="Old Supplier", email="old@supplier.example", lead_time_days=3, is_active=False)
    db.add(s)
    db.flush()
    return s


@pytest.fixture
def product(db: Session, supplier: Supplier) -> Product:
    p = Product(
        sku="WM-001",
        name="Wireless Mouse",
        category="Electronics",
        current_stock=12,
        reorder_point=20,
        minimum_stock=10,
        reorder_quantity=100,
        unit_cost=Decimal("8.50"),
        supplier=supplier,
    )
    db.add(p)
    db.flush()
    return p
