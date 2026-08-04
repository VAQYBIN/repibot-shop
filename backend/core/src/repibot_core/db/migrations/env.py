"""Окружение Alembic.

Работает синхронным драйвером: миграции запускаются отдельным одноразовым
процессом, асинхронность там ничего не даёт.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from repibot_core.db.base import Base
from repibot_core.db.models import User  # noqa: F401 — регистрация в метаданных
from repibot_core.settings import get_settings

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    """Адрес базы для миграций.

    Приоритет у явно переданного в конфиг — так делают тесты. Иначе берётся
    из настроек приложения: адрес один на всё развёртывание, отличается только
    драйвер (asyncpg у приложения, psycopg у Alembic).
    """
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    return get_settings().database_url.replace("+asyncpg", "+psycopg")


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {}) or {}
    section["sqlalchemy.url"] = database_url()

    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
