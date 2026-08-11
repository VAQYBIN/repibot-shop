"""Ключ дедупликации вместо заказа.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_deliveries",
        sa.Column("dedup_key", sa.String(length=160), nullable=True),
    )
    # Существующие строки все до одной про заказ: восстанавливаем ту же форму
    # ключа, которую с этого момента собирает сервис.
    op.execute("update notification_deliveries set dedup_key = 'order:' || order_id || ':' || kind")
    op.alter_column("notification_deliveries", "dedup_key", nullable=False)
    op.alter_column("notification_deliveries", "order_id", nullable=True)
    op.drop_constraint("uq_notification_deliveries_dedup", "notification_deliveries")
    op.create_unique_constraint(
        "uq_notification_deliveries_dedup", "notification_deliveries", ["dedup_key", "channel"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_notification_deliveries_dedup", "notification_deliveries")
    op.execute("delete from notification_deliveries where order_id is null")
    op.alter_column("notification_deliveries", "order_id", nullable=False)
    op.create_unique_constraint(
        "uq_notification_deliveries_dedup",
        "notification_deliveries",
        ["order_id", "kind", "channel"],
    )
    op.drop_column("notification_deliveries", "dedup_key")
