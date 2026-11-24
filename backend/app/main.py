from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import alerts, health, inventory, products, sales, suppliers
from app.core.config import get_settings
from app.services.exceptions import ServiceError

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")


@app.exception_handler(ServiceError)
async def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


app.include_router(health.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(suppliers.router, prefix="/api")
app.include_router(inventory.router, prefix="/api")
app.include_router(sales.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
