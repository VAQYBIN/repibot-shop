"""Окружение Alembic.

Работает синхронным драйвером: миграции запускаются отдельным одноразовым
процессом, асинхронность там ничего не даёт.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from repibot_core.db.base import Base
from repibot_core.db.models import User  # noqa: F401 — регистрация в метаданных

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
