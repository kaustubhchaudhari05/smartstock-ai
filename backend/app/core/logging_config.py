import logging


def configure_logging(level: int = logging.INFO) -> None:
    """Show the app's own log lines (uvicorn only configures its loggers). Idempotent."""
    app_logger = logging.getLogger("app")
    if not any(getattr(h, "_smartstock", False) for h in app_logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        handler._smartstock = True  # type: ignore[attr-defined]
        app_logger.addHandler(handler)
    app_logger.setLevel(level)
