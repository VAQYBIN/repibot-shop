"""Промокоды для атомарных резервов.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "promo_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("percent_off", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bonus_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("per_user_limit", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("code", name="uq_promo_codes_code"),
        sa.CheckConstraint(
            "percent_off >= 0 AND percent_off <= 100", name="ck_promos_percent_range"
        ),
        sa.CheckConstraint("bonus_days >= 0", name="ck_promos_bonus_nonnegative"),
        sa.CheckConstraint("max_uses IS NULL OR max_uses > 0", name="ck_promos_max_uses_positive"),
        sa.CheckConstraint(
            "per_user_limit IS NULL OR per_user_limit > 0", name="ck_promos_user_limit_positive"
        ),
    )
    op.create_foreign_key(
        "fk_promo_reservations_promo_code",
        "promo_reservations",
        "promo_codes",
        ["promo_code_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_promo_reservations_promo_code", "promo_reservations", type_="foreignkey")
    op.drop_table("promo_codes")
