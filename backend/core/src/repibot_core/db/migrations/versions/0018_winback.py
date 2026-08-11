"""Лесенка возврата: учёт ступеней, личный промокод, тип токена и источник дней.

Revision ID: 0018
Revises: 0017

Значения нативных перечислений добавляются здесь и нигде в этой же миграции не
используются: Postgres запрещает применять только что добавленное значение до
конца транзакции, которая его добавила.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "winback_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "uq_winback_grants_telegram",
        "winback_grants",
        ["telegram_id", "step"],
        unique=True,
        postgresql_where=sa.text("telegram_id IS NOT NULL"),
    )
    op.create_index(
        "uq_winback_grants_user",
        "winback_grants",
        ["user_id", "step"],
        unique=True,
        postgresql_where=sa.text("telegram_id IS NULL"),
    )
    op.add_column("promo_codes", sa.Column("target_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_promo_codes_target_user_id",
        "promo_codes",
        "users",
        ["target_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute("alter type one_time_token_type add value if not exists 'winback_days'")
    op.execute("alter type subscription_source add value if not exists 'winback'")
    op.execute("alter type subscription_event_type add value if not exists 'winback'")


def downgrade() -> None:
    # Postgres не умеет удалять значение перечисления. Откат оставляет их на
    # месте: они безвредны, а пересоздание типа переписало бы все таблицы,
    # которые на него ссылаются.
    op.drop_constraint("fk_promo_codes_target_user_id", "promo_codes", type_="foreignkey")
    op.drop_column("promo_codes", "target_user_id")
    op.drop_index("uq_winback_grants_user", table_name="winback_grants")
    op.drop_index("uq_winback_grants_telegram", table_name="winback_grants")
    op.drop_table("winback_grants")
