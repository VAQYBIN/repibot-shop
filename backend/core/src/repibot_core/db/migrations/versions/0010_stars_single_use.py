"""Делает авторизацию и списание по каждому инвойсу Stars долговечными.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payment_attempts", sa.Column("stars_pre_checkout_id", sa.String(255), nullable=True)
    )
    op.add_column(
        "payment_attempts",
        sa.Column("stars_authorized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "payment_attempts",
        sa.Column("telegram_payment_charge_id", sa.String(255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_attempts_stars_pre_checkout_id", "payment_attempts", ["stars_pre_checkout_id"]
    )
    op.create_unique_constraint(
        "uq_attempts_telegram_payment_charge_id",
        "payment_attempts",
        ["telegram_payment_charge_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_attempts_telegram_payment_charge_id", "payment_attempts", type_="unique")
    op.drop_constraint("uq_attempts_stars_pre_checkout_id", "payment_attempts", type_="unique")
    op.drop_column("payment_attempts", "telegram_payment_charge_id")
    op.drop_column("payment_attempts", "stars_authorized_at")
    op.drop_column("payment_attempts", "stars_pre_checkout_id")
