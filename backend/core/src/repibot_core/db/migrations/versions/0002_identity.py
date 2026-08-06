"""Идентичность: способы входа, сессии, одноразовые токены, журнал, outbox.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# create_type=False: типы создаются явным вызовом ниже. Без этого флага
# CREATE TABLE и ADD COLUMN пытаются создать тип ещё раз и падают на
# DuplicateObject — Postgres не умеет CREATE TYPE IF NOT EXISTS.
_ROLE = postgresql.ENUM("user", "support", "admin", name="user_role", create_type=False)
_STATUS = postgresql.ENUM("active", "banned", name="user_status", create_type=False)
_TOKEN_TYPE = postgresql.ENUM(
    "email_verify", "password_reset", "email_change", name="one_time_token_type", create_type=False
)


def upgrade() -> None:
    _ROLE.create(op.get_bind())
    _STATUS.create(op.get_bind())
    _TOKEN_TYPE.create(op.get_bind())

    op.add_column("users", sa.Column("email", sa.String(320), nullable=True))
    op.add_column(
        "users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("telegram_id", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("telegram_username", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("name", sa.String(128), nullable=True))
    op.add_column("users", sa.Column("language", sa.String(2), nullable=False, server_default="ru"))
    op.add_column("users", sa.Column("role", _ROLE, nullable=False, server_default="user"))
    op.add_column("users", sa.Column("status", _STATUS, nullable=False, server_default="active"))
    op.add_column("users", sa.Column("referral_code", sa.String(16), nullable=False))
    op.add_column("users", sa.Column("referred_by_id", sa.Integer(), nullable=True))
    op.add_column(
        "users", sa.Column("remnawave_uuid", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("users", sa.Column("remnawave_short_uuid", sa.String(64), nullable=True))

    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_unique_constraint("uq_users_telegram_id", "users", ["telegram_id"])
    op.create_unique_constraint("uq_users_referral_code", "users", ["referral_code"])
    op.create_foreign_key(
        "fk_users_referred_by_id_users",
        "users",
        "users",
        ["referred_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("previous_token_hash", sa.String(64), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(256), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "one_time_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", _TOKEN_TYPE, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=True),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_outbox_pending", "outbox", ["available_at", "processed_at"])


def downgrade() -> None:
    op.drop_index("ix_outbox_pending", table_name="outbox")
    op.drop_table("outbox")
    op.drop_table("audit_log")
    op.drop_table("one_time_tokens")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_constraint("fk_users_referred_by_id_users", "users", type_="foreignkey")
    for constraint in ("uq_users_referral_code", "uq_users_telegram_id", "uq_users_email"):
        op.drop_constraint(constraint, "users", type_="unique")
    for column in (
        "remnawave_short_uuid",
        "remnawave_uuid",
        "referred_by_id",
        "referral_code",
        "status",
        "role",
        "language",
        "name",
        "telegram_username",
        "telegram_id",
        "password_hash",
        "email_verified_at",
        "email",
    ):
        op.drop_column("users", column)

    _TOKEN_TYPE.drop(op.get_bind())
    _STATUS.drop(op.get_bind())
    _ROLE.drop(op.get_bind())
