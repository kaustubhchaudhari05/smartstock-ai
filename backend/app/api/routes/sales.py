from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession
from app.schemas.sale import SaleCreate, SaleRead, SaleRecorded
from app.schemas.sales_analytics import SalesAnalytics
from app.services import sales_analytics, sales_service

router = APIRouter(prefix="/sales", tags=["sales"])


@router.get("/analytics", response_model=SalesAnalytics)
def sales_analytics_report(
    db: DbSession,
    product_id: Annotated[
        int | None, Query(description="One product, with its 30-day daily series")
    ] = None,
    include_inactive: bool = False,
):
    """Deterministic sales metrics: 7/30-day units, average daily demand, days remaining, trend."""
    return sales_analytics.get_analytics(
        db, product_id=product_id, include_inactive=include_inactive
    )


@router.get("", response_model=list[SaleRead])
def list_sales(
    db: DbSession,
    product_id: int | None = None,
    date_from: Annotated[datetime | None, Query(description="Inclusive, ISO 8601")] = None,
    date_to: Annotated[datetime | None, Query(description="Exclusive, ISO 8601")] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    return sales_service.list_sales(
        db, product_id=product_id, date_from=date_from, date_to=date_to, skip=skip, limit=limit
    )


@router.post("", response_model=SaleRecorded, status_code=status.HTTP_201_CREATED)
def record_sale(data: SaleCreate, db: DbSession):
    return sales_service.record_sale(db, data)
