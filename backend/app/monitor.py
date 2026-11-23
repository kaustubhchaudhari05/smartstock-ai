"""Run one inventory monitoring pass.

Usage (from backend/):
    python -m app.monitor

Creates/updates/resolves stock alerts for every product. Scheduled runs come with
Celery in Phase 8; stock movements and sales also re-check their product immediately.
"""

import sys

from app.core.database import SessionLocal
from app.services.alert_service import run_inventory_check


def main() -> int:
    with SessionLocal() as db:
        summary = run_inventory_check(db)
    print(
        f"Checked {summary.products_checked} products: "
        f"{summary.alerts_created} alerts created, {summary.alerts_updated} updated, "
        f"{summary.alerts_resolved} resolved."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
