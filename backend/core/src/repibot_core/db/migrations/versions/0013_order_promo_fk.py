"""Внешний ключ промокода в заказе.

Ключа не было, пока таблицы промокодов не существовало: коммерческий
фундамент не должен был зависеть от сервиса, которого ещё нет. Сервис давно
на месте, а голое число позволяет заказу ссылаться в никуда.

Данные чистить не нужно: промокоды не удаляются, а снимаются с продажи.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_foreign_key(None, "orders", "promo_codes", ["promo_code_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("orders_promo_code_id_fkey", "orders", type_="foreignkey")
