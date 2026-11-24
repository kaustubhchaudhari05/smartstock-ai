from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.models import AlertSeverity, AlertStatus, AlertType
from app.schemas.alert import AlertDetail, AlertRead, AlertUpdate
from app.services import alert_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertRead])
def list_alerts(
    db: DbSession,
    status: AlertStatus | None = None,
    unresolved_only: Annotated[bool, Query(description="OPEN and ACKNOWLEDGED only")] = False,
    alert_type: AlertType | None = None,
    severity: AlertSeverity | None = None,
    product_id: int | None = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    return alert_service.list_alerts(
        db,
        status=status.value if status else None,
        unresolved_only=unresolved_only,
        alert_type=alert_type.value if alert_type else None,
        severity=severity.value if severity else None,
        product_id=product_id,
        skip=skip,
        limit=limit,
    )


@router.get("/{alert_id}", response_model=AlertDetail)
def get_alert(alert_id: int, db: DbSession):
    return alert_service.get_alert(db, alert_id)


@router.patch("/{alert_id}", response_model=AlertDetail)
def update_alert(alert_id: int, data: AlertUpdate, db: DbSession):
    """Acknowledge (`ACKNOWLEDGED`) or un-acknowledge (`OPEN`) an alert.
    `RESOLVED` is set automatically by monitoring and is rejected here."""
    return alert_service.update_alert_status(db, alert_id, data.status)
