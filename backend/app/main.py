from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.ai.client import (
    LLMError,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.api.routes import alerts, health, inventory, products, recommendations, sales, suppliers
from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.services.exceptions import ServiceError

settings = get_settings()
configure_logging()

app = FastAPI(title=settings.app_name, version="0.1.0")


@app.exception_handler(ServiceError)
async def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


def llm_error_status(exc: LLMError) -> int:
    if isinstance(exc, LLMRateLimitError):
        return 429
    if isinstance(exc, LLMTimeoutError):
        return 504
    if isinstance(exc, (LLMNotConfiguredError, LLMUnavailableError)):
        return 503
    return 502  # invalid or unusable answer from the AI service


@app.exception_handler(LLMError)
async def llm_error_handler(_: Request, exc: LLMError) -> JSONResponse:
    """AI failures never become 500s; messages never contain keys, prompts or responses."""
    headers = {}
    if isinstance(exc, LLMRateLimitError) and exc.retry_after_seconds is not None:
        headers["Retry-After"] = str(max(1, round(exc.retry_after_seconds)))
    return JSONResponse(
        status_code=llm_error_status(exc), content={"detail": str(exc)}, headers=headers
    )


app.include_router(health.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(suppliers.router, prefix="/api")
app.include_router(inventory.router, prefix="/api")
app.include_router(sales.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(recommendations.router, prefix="/api")
