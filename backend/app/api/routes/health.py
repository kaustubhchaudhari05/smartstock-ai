import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health() -> dict[str, str]:
    """Application liveness check."""
    settings = get_settings()
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


@router.get("/db")
def health_db(db: Session = Depends(get_db)) -> dict[str, str]:
    """Database connectivity check."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # Log the error type only; connection errors can contain credentials.
        logger.error("Database health check failed", exc_info=False)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "error", "database": "unreachable"},
        )
    return {"status": "ok", "database": "connected"}
