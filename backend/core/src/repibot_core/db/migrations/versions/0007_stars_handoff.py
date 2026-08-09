"""Непрозрачная ссылка browser → bot для конкретной попытки Stars.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payment_attempts", sa.Column("handoff_token", sa.String(128), nullable=True))
    op.create_unique_constraint(
        "uq_payment_attempts_handoff_token", "payment_attempts", ["handoff_token"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_payment_attempts_handoff_token", "payment_attempts", type_="unique")
    op.drop_column("payment_attempts", "handoff_token")
