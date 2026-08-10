"""Действующая карта пользователя и привязка без списания.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# create_type=False по той же причине, что и в 0002: без флага CREATE TABLE
# пытается создать тип ещё раз и падает на DuplicateObject. payment_provider
# существует с 0006, а card_binding_status создаётся явно ниже.
_PROVIDER = postgresql.ENUM("yookassa", "stars", name="payment_provider", create_type=False)
_BINDING_STATUS = postgresql.ENUM(
    "pending", "active", "failed", name="card_binding_status", create_type=False
)


def upgrade() -> None:
    _BINDING_STATUS.create(op.get_bind())
    op.create_table(
        "saved_payment_methods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", _PROVIDER, nullable=False),
        sa.Column("provider_method_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    # Частичный индекс, а не проверка в коде: две действующие карты означали бы
    # списание с той, о которой пользователь уже забыл.
    op.create_index(
        "uq_saved_methods_active",
        "saved_payment_methods",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_table(
        "card_bindings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", _PROVIDER, nullable=False),
        sa.Column("provider_binding_id", sa.String(255), nullable=True),
        sa.Column("status", _BINDING_STATUS, nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("provider", "provider_binding_id", name="uq_card_bindings_provider_id"),
    )


def downgrade() -> None:
    op.drop_table("card_bindings")
    op.drop_index("uq_saved_methods_active", table_name="saved_payment_methods")
    op.drop_table("saved_payment_methods")
    _BINDING_STATUS.drop(op.get_bind(), checkfirst=True)
