"""Рабочее место поддержки: метка состояния темы и заглушение.

Revision ID: 0019
Revises: 0018

Обе колонки допускают пустоту и на существующих строках остаются пустыми:
у прежних обращений метка появится при первом же движении, а заглушённых до
этой миграции не было вовсе.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # create_type=False: перечисление статусов обращения создано миграцией
    # 0017, и повторное создание оборвало бы обновление живой базы.
    status = postgresql.ENUM(name="ticket_status", create_type=False)
    op.add_column("tickets", sa.Column("topic_status_mark", status, nullable=True))
    op.add_column("users", sa.Column("support_muted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "support_muted_at")
    op.drop_column("tickets", "topic_status_mark")
