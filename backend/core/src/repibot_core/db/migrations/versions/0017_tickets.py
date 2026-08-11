"""Обращения в поддержку и их переписка.

Revision ID: 0017
Revises: 0016
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

# create_type=False по той же причине, что и в 0016: иначе CREATE TABLE пробует
# создать тип второй раз и падает на DuplicateObject. Оба типа заводятся явно,
# и downgrade их так же явно удаляет.
_TICKET_STATUS = postgresql.ENUM(
    "waiting_staff", "waiting_user", "closed", name="ticket_status", create_type=False
)
_TICKET_AUTHOR = postgresql.ENUM("user", "staff", "system", name="ticket_author", create_type=False)


def upgrade() -> None:
    _TICKET_STATUS.create(op.get_bind())
    _TICKET_AUTHOR.create(op.get_bind())
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", _TICKET_STATUS, nullable=False),
        sa.Column("subject", sa.String(120), nullable=False),
        sa.Column("telegram_topic_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_user_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_staff_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    # Очередь персонала — «что ждёт ответа дольше всех».
    op.create_index("ix_tickets_queue", "tickets", ["status", "last_user_message_at"])
    op.create_index("ix_tickets_user", "tickets", ["user_id", "created_at"])
    op.create_index(
        "uq_tickets_topic",
        "tickets",
        ["telegram_topic_id"],
        unique=True,
        postgresql_where=sa.text("telegram_topic_id IS NOT NULL"),
    )
    op.create_table(
        "ticket_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("author_kind", _TICKET_AUTHOR, nullable=False),
        sa.Column("author_user_id", sa.Integer(), nullable=True),
        sa.Column("author_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("telegram_message_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ticket_messages_thread", "ticket_messages", ["ticket_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ticket_messages_thread", table_name="ticket_messages")
    op.drop_table("ticket_messages")
    op.drop_index("uq_tickets_topic", table_name="tickets")
    op.drop_index("ix_tickets_user", table_name="tickets")
    op.drop_index("ix_tickets_queue", table_name="tickets")
    op.drop_table("tickets")
    _TICKET_AUTHOR.drop(op.get_bind(), checkfirst=True)
    _TICKET_STATUS.drop(op.get_bind(), checkfirst=True)
