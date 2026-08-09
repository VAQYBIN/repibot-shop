"""Миграции должны применяться на чистой базе и откатываться обратно."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_core.db.base import Base
from repibot_core.db.engine import check_database, create_engine
from repibot_core.db.models import User  # noqa: F401 — регистрация в метаданных

pytestmark = pytest.mark.docker


def _alembic_config(url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("+asyncpg", "+psycopg"))
    return config


def test_migrations_apply_and_rollback(postgres_url: str) -> None:
    config = _alembic_config(postgres_url)

    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def test_promo_bonus_snapshot_migration_refuses_legacy_pending_reservation(
    postgres_url: str,
) -> None:
    """A zero default would silently lose a promised bonus on a pending paid order."""
    config = _alembic_config(postgres_url)
    command.downgrade(config, "base")
    command.upgrade(config, "0008")
    engine = create_sync_engine(postgres_url.replace("+asyncpg", "+psycopg"))
    try:
        with engine.begin() as connection:
            user_id = connection.execute(
                text(
                    "insert into users (email, language, role, status, referral_code) "
                    "values ('legacy@example.org', 'ru', 'user', 'active', 'LEGACY') returning id"
                )
            ).scalar_one()
            plan_id = connection.execute(
                text(
                    "insert into plans (code, name, duration_days, price_rub, price_stars, "
                    "traffic_reset_strategy, internal_squad_uuids) values "
                    "('legacy', '{\"ru\": \"legacy\"}'::jsonb, 30, 300, 199, 'NO_RESET', "
                    "array['11111111-1111-4111-8111-111111111111']::uuid[]) returning id"
                )
            ).scalar_one()
            promo_id = connection.execute(
                text("insert into promo_codes (code, bonus_days) values ('LEGACY', 5) returning id")
            ).scalar_one()
            order_id = connection.execute(
                text(
                    "insert into orders (user_id, purpose, plan_id, plan_code_snapshot, "
                    "plan_name_snapshot, duration_days_snapshot, price_rub_snapshot, "
                    "price_stars_snapshot, gross_rub, discount_rub, amount_due_rub, promo_code_id, "
                    "client_key, expires_at, status) values "
                    "(:user_id, 'purchase', :plan_id, 'legacy', '{\"ru\": \"legacy\"}'::jsonb, "
                    "30, 300, 199, 300, 0, 300, :promo_id, 'legacy-order', "
                    "now() + interval '30 minutes', "
                    "'pending') returning id"
                ),
                {"user_id": user_id, "plan_id": plan_id, "promo_id": promo_id},
            ).scalar_one()
            connection.execute(
                text(
                    "insert into promo_reservations (order_id, promo_code_id, user_id, expires_at) "
                    "values (:order_id, :promo_id, :user_id, now() + interval '30 minutes')"
                ),
                {"order_id": order_id, "promo_id": promo_id, "user_id": user_id},
            )
        with pytest.raises(RuntimeError, match="pending promo reservations"):
            command.upgrade(config, "0009")
    finally:
        engine.dispose()
        # This fixture shares the PostgreSQL container with the remaining migration tests.
        # The deliberately blocked 0009 leaves its legacy fixture at revision 0008.
        command.downgrade(config, "base")


async def test_users_table_exists_after_migration(postgres_url: str, engine: AsyncEngine) -> None:
    command.upgrade(_alembic_config(postgres_url), "head")

    async with engine.connect() as connection:
        result = await connection.execute(
            text("select column_name from information_schema.columns where table_name = 'users'")
        )
        columns = {row[0] for row in result}

    assert {"id", "created_at", "updated_at"} <= columns


async def test_identity_columns_exist(postgres_url: str, engine: AsyncEngine) -> None:
    command.upgrade(_alembic_config(postgres_url), "head")

    async with engine.connect() as connection:
        result = await connection.execute(
            text("select column_name from information_schema.columns where table_name = 'users'")
        )
        columns = {row[0] for row in result}

    assert {
        "email",
        "email_verified_at",
        "password_hash",
        "telegram_id",
        "telegram_username",
        "name",
        "language",
        "role",
        "status",
        "referral_code",
        "referred_by_id",
        "remnawave_id",
        "remnawave_short_uuid",
        "remnawave_subscription_url",
    } <= columns


async def test_identity_tables_exist(postgres_url: str, engine: AsyncEngine) -> None:
    command.upgrade(_alembic_config(postgres_url), "head")

    async with engine.connect() as connection:
        result = await connection.execute(
            text("select table_name from information_schema.tables where table_schema = 'public'")
        )
        tables = {row[0] for row in result}

    assert {"sessions", "one_time_tokens", "audit_log", "outbox"} <= tables


async def test_email_is_unique(postgres_url: str, engine: AsyncEngine) -> None:
    """Уникальность почты держит база, а не проверка в сервисе.

    Две одновременные регистрации на один адрес проходят проверку «занят ли»
    обе, и без ограничения в схеме в базе появятся два аккаунта.
    """
    command.upgrade(_alembic_config(postgres_url), "head")

    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into users (email, language, role, status, referral_code) "
                "values ('a@example.org', 'ru', 'user', 'active', 'CODE1')"
            )
        )
        with pytest.raises(IntegrityError):
            await connection.execute(
                text(
                    "insert into users (email, language, role, status, referral_code) "
                    "values ('a@example.org', 'ru', 'user', 'active', 'CODE2')"
                )
            )


def test_migrations_match_the_models(postgres_url: str) -> None:
    """Модель и миграции расходятся молча.

    Правку модели без новой миграции обнаружит только продакшен: приложение
    обращается к столбцу, которого в базе нет. Autogenerate сравнивает
    фактическую схему с метаданными и показывает разницу до выката.
    """
    command.upgrade(_alembic_config(postgres_url), "head")

    engine = create_sync_engine(postgres_url.replace("+asyncpg", "+psycopg"))
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"compare_type": True, "target_metadata": Base.metadata}
            )
            difference = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert difference == [], f"схема разошлась с моделями: {difference}"


async def test_check_database_returns_true_when_reachable(engine: AsyncEngine) -> None:
    assert await check_database(engine) is True


async def test_check_database_returns_false_when_unreachable() -> None:
    engine = create_engine("postgresql+asyncpg://nobody:nobody@127.0.0.1:1/nothing")
    try:
        assert await check_database(engine) is False
    finally:
        await engine.dispose()
