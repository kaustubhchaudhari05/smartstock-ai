"""remove overstocked alert type

Revision ID: d3d9bd16ab2f
Revises: 0ee178b4881e
Create Date: 2026-11-23 16:07:06.541310

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3d9bd16ab2f'
down_revision: Union[str, None] = '0ee178b4881e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINT = "ck_inventory_alerts_alert_type_valid"


def upgrade() -> None:
    # OVERSTOCKED is out of scope; fails loudly if any such alert exists.
    op.drop_constraint(op.f(CONSTRAINT), "inventory_alerts", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT), "inventory_alerts", "alert_type IN ('LOW_STOCK', 'OUT_OF_STOCK')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "inventory_alerts", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT),
        "inventory_alerts",
        "alert_type IN ('LOW_STOCK', 'OUT_OF_STOCK', 'OVERSTOCKED')",
    )
