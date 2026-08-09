"""Неизменяемые bonus days зарезервированного промокода.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SHARE ROW EXCLUSIVE conflicts with the ROW EXCLUSIVE locks needed for
    # checkout inserts. Lock both tables before inspection: an in-flight
    # pre-0009 checkout cannot create its order/reservation between count and ALTER.
    op.execute(sa.text("LOCK TABLE orders, promo_reservations IN SHARE ROW EXCLUSIVE MODE"))
    pending = op.get_bind().scalar(
        sa.text(
            "select count(*) from promo_reservations reservation "
            "join orders on orders.id = reservation.order_id "
            "where reservation.consumed_at is null and orders.status = 'pending'"
        )
    )
    if pending:
        raise RuntimeError(
            f"migration 0009 blocked: {pending} pending promo reservations lack an immutable "
            "bonus snapshot. Let the 30-minute pending promo orders drain or expire, or cancel "
            "them before applying this migration."
        )
    op.add_column(
        "promo_reservations",
        sa.Column("bonus_days_snapshot", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("promo_reservations", "bonus_days_snapshot")
