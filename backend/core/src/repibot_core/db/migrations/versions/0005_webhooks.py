"""События вебхуков и расхождения сверки.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

WEBHOOK_SOURCE = sa.Enum("remnawave", "yookassa", name="webhook_source")
FINDING_ACTION = sa.Enum("fixed", "skipped", name="reconciliation_action")


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", WEBHOOK_SOURCE, nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        # Идемпотентность держит база: две одновременные доставки одного
        # события проходят проверку «принимали ли» обе.
        sa.UniqueConstraint("source", "event_id", name="uq_webhook_events_source_id"),
    )

    op.create_table(
        "reconciliation_findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("ours", sa.String(512), nullable=True),
        sa.Column("theirs", sa.String(512), nullable=True),
        sa.Column("action", FINDING_ACTION, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Отчёт читается прогоном целиком, а не построчно.
    op.create_index("ix_reconciliation_findings_run", "reconciliation_findings", ["run_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_reconciliation_findings_run", table_name="reconciliation_findings")
    op.drop_table("reconciliation_findings")
    op.drop_table("webhook_events")

    # Типы перечислений таблицы не уносят: без явного удаления повторный
    # upgrade наткнётся на уже существующий тип.
    for enum_type in (FINDING_ACTION, WEBHOOK_SOURCE):
        enum_type.drop(op.get_bind(), checkfirst=True)
