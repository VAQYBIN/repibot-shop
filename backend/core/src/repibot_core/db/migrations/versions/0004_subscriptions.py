"""Тарифы, подписки, журнал начислений, выданные триалы.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TRAFFIC_STRATEGY = sa.Enum(
    "NO_RESET", "DAY", "WEEK", "MONTH", "MONTH_ROLLING", name="traffic_reset_strategy"
)
SUBSCRIPTION_STATUS = sa.Enum(
    "trial", "active", "expired", "disabled", "pending_provision", name="subscription_status"
)
SUBSCRIPTION_SOURCE = sa.Enum("trial", "purchase", "gift", "admin", name="subscription_source")
SUBSCRIPTION_ACTOR = sa.Enum("user", "admin", "system", name="subscription_actor")
EVENT_TYPE = sa.Enum(
    "trial",
    "purchase",
    "renew",
    "plan_change",
    "bonus_days",
    "gift",
    "expired",
    "admin_grant",
    "admin_revoke",
    name="subscription_event_type",
)


def upgrade() -> None:
    # Панель 3.2.1 адресует пользователя числом. Данных в поле ещё нет —
    # подписки не выдавались, — поэтому колонка заменяется, а не переносится.
    op.drop_column("users", "remnawave_uuid")
    op.add_column("users", sa.Column("remnawave_id", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("remnawave_subscription_url", sa.String(512), nullable=True))
    op.create_unique_constraint("uq_users_remnawave_id", "users", ["remnawave_id"])

    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", postgresql.JSONB(), nullable=False),
        sa.Column("description", postgresql.JSONB(), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("price_rub", sa.Numeric(10, 2), nullable=False),
        sa.Column("price_stars", sa.Integer(), nullable=False),
        sa.Column("traffic_limit_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("traffic_reset_strategy", TRAFFIC_STRATEGY, nullable=False),
        sa.Column("hwid_device_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "internal_squad_uuids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=False)),
            nullable=False,
        ),
        sa.Column("is_trial", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    # Активный триальный тариф ровно один: иначе «какой триал выдать» —
    # вопрос без ответа. Условие индекса оставляет в нём только такие строки,
    # и уникальность по is_trial означает «строка ровно одна».
    op.create_index(
        "uq_plans_single_active_trial",
        "plans",
        ["is_trial"],
        unique=True,
        postgresql_where=sa.text("is_trial AND is_active"),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("status", SUBSCRIPTION_STATUS, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("auto_renew_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", SUBSCRIPTION_SOURCE, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    # Крон истечения выбирает по дате и статусу — без индекса это полный
    # проход по таблице каждый час.
    op.create_index("ix_subscriptions_expires_at", "subscriptions", ["status", "expires_at"])

    op.create_table(
        "subscription_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", EVENT_TYPE, nullable=False),
        sa.Column("days_delta", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=True),
        sa.Column("actor", SUBSCRIPTION_ACTOR, nullable=False),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("comment", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_subscription_events_user_id", "subscription_events", ["user_id", "created_at"]
    )

    op.create_table(
        "trial_grants",
        sa.Column("telegram_id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("trial_grants")
    op.drop_index("ix_subscription_events_user_id", table_name="subscription_events")
    op.drop_table("subscription_events")
    op.drop_index("ix_subscriptions_expires_at", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_index("uq_plans_single_active_trial", table_name="plans")
    op.drop_table("plans")

    op.drop_constraint("uq_users_remnawave_id", "users", type_="unique")
    op.drop_column("users", "remnawave_subscription_url")
    op.drop_column("users", "remnawave_id")
    op.add_column(
        "users", sa.Column("remnawave_uuid", postgresql.UUID(as_uuid=True), nullable=True)
    )

    for enum_type in (
        EVENT_TYPE,
        SUBSCRIPTION_ACTOR,
        SUBSCRIPTION_SOURCE,
        SUBSCRIPTION_STATUS,
        TRAFFIC_STRATEGY,
    ):
        enum_type.drop(op.get_bind(), checkfirst=True)
