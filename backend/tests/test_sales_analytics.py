from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import Product, Sale
from app.schemas.sales_analytics import SalesTrend
from app.services import sales_analytics as sa
from app.services.exceptions import NotFoundError

AS_OF = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
TODAY = AS_OF.date()
D = Decimal


# ---------- pure calculations ----------


def test_daily_series_is_zero_filled_and_ordered():
    series = sa.daily_series({date(2026, 11, 22): 5, date(2026, 11, 24): 2}, TODAY, 3)
    assert [(d.date.day, d.units_sold) for d in series] == [(22, 5), (23, 0), (24, 2)]


@pytest.mark.parametrize("units, days, expected", [(150, 30, "5.00"), (10, 7, "1.43"), (0, 30, "0.00"), (1, 30, "0.03")])
def test_average_daily(units, days, expected):
    assert sa.average_daily(units, days) == D(expected)


@pytest.mark.parametrize(
    "stock, units_30d, expected",
    [
        (12, 150, D("2.4")),    # CLAUDE.md example: 12 units / 5 per day
        (0, 150, D("0.0")),     # out of stock with demand
        (100, 0, None),         # no sales: safe, no division by zero
        (0, 0, None),
        (10, 7, D("42.9")),     # exact: 10 * 30 / 7 = 42.857... (not 10 / 0.23 = 43.5)
    ],
)
def test_days_remaining(stock, units_30d, expected):
    assert sa.days_remaining(stock, units_30d) == expected


@pytest.mark.parametrize(
    "units_7d, units_30d, expected",
    [
        (0, 0, SalesTrend.INSUFFICIENT_DATA),
        (7, 30, SalesTrend.STABLE),        # 1.0/day both
        (70, 300, SalesTrend.STABLE),
        (14, 30, SalesTrend.INCREASING),   # 2.0/day vs 1.0/day
        (2, 30, SalesTrend.DECREASING),    # 0.29/day vs 1.0/day
        (0, 30, SalesTrend.DECREASING),    # sales stopped this week
        (7, 7, SalesTrend.INCREASING),     # all 30-day sales happened this week (new product)
    ],
)
def test_sales_trend(units_7d, units_30d, expected):
    assert sa.sales_trend(units_7d, units_30d) is expected


def test_trend_threshold_is_strict():
    # ratio = (u7 * 30) / (u30 * 7). With u30 = 600: u7 = 161 -> 1.15 exactly -> STABLE
    assert sa.sales_trend(161, 600) is SalesTrend.STABLE
    assert sa.sales_trend(162, 600) is SalesTrend.INCREASING   # 1.157
    assert sa.sales_trend(119, 600) is SalesTrend.STABLE       # 0.85 exactly
    assert sa.sales_trend(118, 600) is SalesTrend.DECREASING   # 0.843


# ---------- with the database ----------


def sale_at(db, product, when, qty):
    db.add(Sale(product_id=product.id, quantity_sold=qty, unit_price=D("1.00"), sale_date=when))


def test_product_metrics(db, product):
    # product fixture: WM-001, current stock 12. 5 units every 24h for 30 days -> 150
    for i in range(30):
        sale_at(db, product, AS_OF - timedelta(hours=1 + 24 * i), 5)
    sale_at(db, product, AS_OF - timedelta(days=40), 99)    # outside 30d, counts in total only
    db.commit()

    m = sa.product_metrics(db, product.id, as_of=AS_OF)
    assert (m.units_sold_total, m.units_sold_30d, m.units_sold_7d) == (249, 150, 35)
    assert (m.average_daily_sales, m.average_daily_sales_7d) == (D("5.00"), D("5.00"))
    assert m.days_remaining == D("2.4")
    assert m.trend is SalesTrend.STABLE
    assert len(m.daily_sales) == 30
    assert m.daily_sales[0].date == TODAY - timedelta(days=29) and m.daily_sales[-1].date == TODAY


@pytest.mark.parametrize("hour", [0, 6, 12, 18, 23])
def test_steady_demand_is_stable_at_any_time_of_day(db, product, hour):
    """Regression: calendar-day windows that include a partly elapsed 'today' dragged the
    7-day average down by up to 1/7 (vs 1/30 for the 30-day one), biasing trends toward
    DECREASING. Rolling windows give identical averages for perfectly steady demand."""
    as_of = datetime(2026, 11, 24, hour, 30, tzinfo=timezone.utc)
    for i in range(60):  # one sale every day at 19:00 UTC, up to as_of
        when = datetime(2026, 11, 24, 19, 0, tzinfo=timezone.utc) - timedelta(days=i)
        if when <= as_of:
            sale_at(db, product, when, 4)
    db.commit()
    m = sa.product_metrics(db, product.id, as_of=as_of)
    assert (m.units_sold_7d, m.units_sold_30d) == (28, 120)
    assert m.average_daily_sales_7d == m.average_daily_sales == D("4.00")
    assert m.trend is SalesTrend.STABLE


def test_rolling_window_boundaries(db, product):
    sale_at(db, product, AS_OF - timedelta(days=7), 100)                      # exactly 7d old: outside 7d
    sale_at(db, product, AS_OF - timedelta(days=7) + timedelta(minutes=1), 1)  # just inside
    sale_at(db, product, AS_OF, 2)                                             # exactly now: inside
    sale_at(db, product, AS_OF + timedelta(minutes=1), 50)                     # future: ignored
    db.commit()
    m = sa.product_metrics(db, product.id, as_of=AS_OF)
    assert (m.units_sold_7d, m.units_sold_30d, m.units_sold_total) == (3, 103, 103)


def test_product_without_sales(db, product):
    m = sa.product_metrics(db, product.id, as_of=AS_OF)
    assert (m.units_sold_total, m.units_sold_30d, m.average_daily_sales) == (0, 0, D("0.00"))
    assert m.days_remaining is None
    assert m.trend is SalesTrend.INSUFFICIENT_DATA
    assert [d.units_sold for d in m.daily_sales] == [0] * 30


def test_daily_series_uses_utc_calendar_days(db, product):
    # 23:30 UTC yesterday belongs to yesterday, even though it is already today in India (+05:30)
    sale_at(db, product, datetime(2026, 11, 23, 23, 30, tzinfo=timezone.utc), 3)
    # 02:00 today at +05:30 is 20:30 UTC yesterday
    sale_at(db, product, datetime(2026, 11, 24, 2, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))), 4)
    sale_at(db, product, datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc), 1)
    db.commit()
    series = {d.date: d.units_sold for d in sa.product_metrics(db, product.id, as_of=AS_OF).daily_sales}
    assert (series[TODAY - timedelta(days=1)], series[TODAY]) == (7, 1)


def test_all_product_metrics(db, product):
    other = Product(sku="KB-002", name="Keyboard", category="Electronics", current_stock=40, reorder_point=10,
                    minimum_stock=5, reorder_quantity=20, unit_cost=D("30"))
    inactive = Product(sku="OLD-1", name="Old", category="X", current_stock=1, reorder_point=0,
                       minimum_stock=0, reorder_quantity=0, unit_cost=D("1"), is_active=False)
    db.add_all([other, inactive])
    db.commit()
    for i in range(7):
        sale_at(db, product, AS_OF - timedelta(hours=1 + 24 * i), 4)   # 28 this week only -> INCREASING
    for i in range(7, 30):
        sale_at(db, other, AS_OF - timedelta(hours=1 + 24 * i), 2)     # 46, none this week -> DECREASING
    db.commit()

    metrics = sa.all_product_metrics(db, as_of=AS_OF)
    assert [m.sku for m in metrics] == ["KB-002", "WM-001"]          # active only, by SKU
    kb, wm = metrics
    assert (wm.units_sold_30d, wm.trend, wm.days_remaining) == (28, SalesTrend.INCREASING, D("12.9"))
    assert (kb.units_sold_30d, kb.units_sold_7d, kb.trend) == (46, 0, SalesTrend.DECREASING)
    assert all(m.daily_sales is None for m in metrics)               # series only for single product
    assert [m.sku for m in sa.all_product_metrics(db, as_of=AS_OF, include_inactive=True)] == ["KB-002", "OLD-1", "WM-001"]


def test_unknown_product(db):
    with pytest.raises(NotFoundError):
        sa.product_metrics(db, 999999, as_of=AS_OF)
