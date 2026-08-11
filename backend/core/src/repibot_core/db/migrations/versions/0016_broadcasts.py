"""Кампании рассылки и их зафиксированная аудитория.

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

# create_type=False по той же причине, что и в 0012: иначе CREATE TABLE пробует
# создать тип второй раз и падает на DuplicateObject. Оба типа заводятся явно.
_BROADCAST_STATUS = postgresql.ENUM(
    "draft", "running", "canceled", "done", name="broadcast_status", create_type=False
)
_RECIPIENT_STATUS = postgresql.ENUM(
    "pending", "sent", "failed", name="broadcast_recipient_status", create_type=False
)


def upgrade() -> None:
    _BROADCAST_STATUS.create(op.get_bind())
    _RECIPIENT_STATUS.create(op.get_bind())
    op.create_table(
        "broadcasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("segment", sa.String(32), nullable=False),
        sa.Column("title", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", _BROADCAST_STATUS, nullable=False),
        sa.Column("planned_count", sa.Integer(), nullable=False),
        sa.Column("sent_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_table(
        "broadcast_recipients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("broadcast_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("status", _RECIPIENT_STATUS, nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(512), nullable=True),
        sa.ForeignKeyConstraint(["broadcast_id"], ["broadcasts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        # Уникальность держит база, а не сервис: повторный запуск материализации
        # иначе отправил бы одному человеку два одинаковых письма.
        sa.UniqueConstraint("broadcast_id", "user_id", name="uq_broadcast_recipients_person"),
    )
    op.create_index(
        "ix_broadcast_recipients_queue", "broadcast_recipients", ["broadcast_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_broadcast_recipients_queue", table_name="broadcast_recipients")
    op.drop_table("broadcast_recipients")
    op.drop_table("broadcasts")
    _RECIPIENT_STATUS.drop(op.get_bind(), checkfirst=True)
    _BROADCAST_STATUS.drop(op.get_bind(), checkfirst=True)
