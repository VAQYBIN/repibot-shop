# Идентичность, этап 1a — план реализации

> **Для агентов:** ОБЯЗАТЕЛЬНЫЙ ПОДСКИЛЛ: используйте superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans для выполнения плана задача за задачей. Шаги размечены чекбоксами (`- [ ]`).

**Цель:** дать пользователю аккаунт — регистрация по почте с обязательным подтверждением, вход паролем в вебе и по `initData` в MiniApp, профиль, список сессий, роли.

**Архитектура:** способы входа — взаимозаменяемые верификаторы, возвращающие `VerifiedIdentity`; сессию выдаёт единственный путь в `AuthService`. Access-токен — JWT на 15 минут без роли в claims, refresh — непрозрачная строка в httpOnly cookie с ротацией и обнаружением переиспользования. Письма пишутся в `outbox` в той же транзакции, что и пользователь, и отправляются воркером с ретраями.

**Стек:** Python 3.13, SQLAlchemy 2.0, Alembic, FastAPI, aiogram 3.30, TaskIQ, argon2-cffi, PyJWT, aiosmtplib, Jinja2, Valkey; React 19, Next.js 16, TanStack Query v5, zod, Vitest, Playwright.

**Спецификация:** [docs/superpowers/specs/2026-08-05-identity-design.md](../specs/2026-08-05-identity-design.md)

## Глобальные ограничения

- Ветка работы — `dev`. Отдельные ветки, если понадобятся, создаются от `dev`.
- Каждая задача заканчивается прогоном `uv run check` без ошибок и одним коммитом. Сообщение коммита на русском в формате `тип: краткое описание`.
- Тест пишется первым и падает до реализации.
- Бизнес-логика — только в `backend/core/services` и `backend/core/domain`. В роутерах FastAPI и хендлерах aiogram её нет.
- Комментарии, докстринги и сообщения — на русском. Комментарий объясняет причину решения, а не пересказывает код.
- `mypy` в strict и `ruff` с набором из `pyproject.toml` — блокирующие. Аннотации обязательны везде, включая тесты.
- Новая переменная окружения добавляется одновременно в `Settings`, `.env.example` и `docs/deployment.md`.
- Тексты ошибок API не локализуются: ответ несёт код (`invalid_credentials`, `email_not_verified`, `email_taken`, `weak_password`, `token_invalid`, `token_expired`, `rate_limited`, `last_login_method`, `unauthorized`, `forbidden`, `not_found`, `validation_error`), фразу подбирает фронтенд.
- Секреты в логи не попадают: пароли, токены и `initData` не пишутся ни в сообщениях, ни в `extra`.
- Цвета, отступы и типографика — из `docs/design/repibot-brandbook.md` через токены `packages/ui`. Значений «на глаз» в коде нет.
- Тесты, которым нужен Postgres, помечаются `pytestmark = pytest.mark.docker`.
- `sa.Integer` для `users.id` сохраняется — таблица уже создана в подпроекте 0.
- Модель сессии называется `Session` и при импорте затеняет `sqlalchemy.orm.Session`. В файлах, где нужны оба, ORM-класс берётся как `from sqlalchemy.orm import Session as OrmSession` или обращением через модуль.
- Тестовый `JWT_SECRET` не короче 32 символов: настройки отвергают слабый ключ подписи, и PyJWT предупреждает о нём отдельно.
- Passkey и Telegram OIDC в этот этап не входят: они в плане 1b. Мест «на будущее» под них в коде не оставляем, кроме уже описанной структуры верификаторов.

## Состояние выполнения

Задачи выполнялись волнами: внутри волны — параллельно, между волнами — полный
прогон `uv run check`.

| Волна | Задачи | Состояние |
|---|---|---|
| 1 | 1 настройки, 2 схема, 4 пароли и токены, 13 лимиты | готово |
| 2 | 3 домен | готово |
| 3 | 5 репозитории | готово |
| 4 | 6 очередь, 8 кэш роли | готово |
| 5 | 7 письма, 9 сессии | готово |
| 6 | 10 вход паролем, 12 MiniApp, 16 бот | готово |
| 7 | 11 профиль, 14 эндпоинты входа | готово |
| 8 | 15 `/api/me` и гейт роли | в работе |
| 9 | 17 типы API | |
| 10 | 18 клиентская аутентификация | |
| 11 | 19 экраны веба, 20 экраны MiniApp | |
| 12 | 21 сквозные тесты и документация | |

Помимо задач плана в этап вошли две правки, найденные при сборке: настройки
отвергают `JWT_SECRET` короче 32 символов, а проверка портов в `compose.yml`
считает рабочий набор, потому что Mailpit живёт под профилем `dev`.

---

## Структура файлов

| Файл | Ответственность |
|---|---|
| `backend/core/src/repibot_core/settings.py` | новые переменные: сроки токенов, почта, админы |
| `backend/core/src/repibot_core/db/models/user.py` | `User`, `UserRole`, `UserStatus` |
| `backend/core/src/repibot_core/db/models/session.py` | `Session` — refresh-сессия браузера |
| `backend/core/src/repibot_core/db/models/one_time_token.py` | `OneTimeToken`, `TokenType` |
| `backend/core/src/repibot_core/db/models/audit.py` | `AuditLog` |
| `backend/core/src/repibot_core/db/models/outbox.py` | `OutboxMessage` |
| `backend/core/src/repibot_core/db/migrations/versions/0002_identity.py` | миграция этапа |
| `backend/core/src/repibot_core/db/repositories/users.py` | доступ к `users` |
| `backend/core/src/repibot_core/db/repositories/sessions.py` | доступ к `sessions` |
| `backend/core/src/repibot_core/db/repositories/tokens.py` | доступ к `one_time_tokens` |
| `backend/core/src/repibot_core/db/repositories/outbox.py` | запись и выборка `outbox` |
| `backend/core/src/repibot_core/db/repositories/audit.py` | запись `audit_log` |
| `backend/core/src/repibot_core/domain/identity.py` | нормализация почты, политика пароля, сроки, коды, `can_unlink` |
| `backend/core/src/repibot_core/security/passwords.py` | Argon2id |
| `backend/core/src/repibot_core/security/tokens.py` | JWT access и непрозрачный refresh |
| `backend/core/src/repibot_core/security/initdata.py` | HMAC-проверка `initData` |
| `backend/core/src/repibot_core/queue.py` | брокер и планировщик TaskIQ (переезд из `repibot_worker`) |
| `backend/core/src/repibot_core/services/outbox.py` | постановка и разбор очереди |
| `backend/core/src/repibot_core/services/auth/service.py` | `AuthService` — единственный путь выдачи сессии |
| `backend/core/src/repibot_core/services/auth/password.py` | верификатор пароля, регистрация, сброс |
| `backend/core/src/repibot_core/services/auth/telegram.py` | верификатор `initData` |
| `backend/core/src/repibot_core/services/auth/types.py` | `VerifiedIdentity`, `IssuedSession`, исключения |
| `backend/core/src/repibot_core/services/profile.py` | профиль, смена почты и пароля, сессии |
| `backend/core/src/repibot_core/services/principal.py` | кэш роли и статуса, отзыв сессий |
| `backend/core/src/repibot_core/integrations/email/sender.py` | интерфейс и реализации отправки |
| `backend/core/src/repibot_core/integrations/email/templates.py` | шаблоны писем на двух языках |
| `backend/core/src/repibot_core/i18n.py` | серверные словари для писем и бота |
| `backend/core/src/repibot_core/ratelimit.py` | скользящее окно на Valkey |
| `backend/api/src/repibot_api/deps.py` | сессия БД, Valkey, `current_user`, `require_role` |
| `backend/api/src/repibot_api/routers/auth.py` | публичные эндпоинты входа и почты |
| `backend/api/src/repibot_api/routers/me.py` | профиль и сессии |
| `backend/api/src/repibot_api/routers/admin.py` | гейт роли |
| `backend/api/src/repibot_api/schemas.py` | Pydantic-схемы запросов и ответов |
| `backend/api/src/repibot_api/cookies.py` | установка и снятие refresh-cookie |
| `backend/bot/src/repibot_bot/handlers/start.py` | `/start` с регистрацией по `telegram_id` |
| `backend/bot/src/repibot_bot/handlers/language.py` | `/language` |
| `backend/bot/src/repibot_bot/middleware.py` | подстановка пользователя и языка |
| `backend/worker/src/repibot_worker/tasks.py` | задача разбора `outbox` |
| `frontend/packages/core/src/auth/store.ts` | access-токен в памяти |
| `frontend/packages/core/src/auth/client.ts` | клиент с single-flight обновлением |
| `frontend/packages/core/src/auth/hooks.ts` | `useMe`, `useLogin`, `useLogout`, мутации |
| `frontend/packages/core/src/auth/schemas.ts` | zod-схемы форм |
| `frontend/packages/ui/src/components/*` | форма, поле пароля, диалог, пустое состояние |
| `frontend/apps/web/src/app/(auth)/*` | вход, регистрация, подтверждение, сброс |
| `frontend/apps/web/src/app/account/*` | профиль и безопасность |
| `frontend/apps/miniapp/src/routes/*` | автовход и профиль |
| `frontend/apps/web/e2e/auth.spec.ts` | сквозные сценарии через Mailpit |

---

## Задача 1: Настройки и окружение

**Файлы:**
- Изменить: `backend/core/src/repibot_core/settings.py`
- Изменить: `.env.example`, `compose.yml`, `docs/deployment.md`, `conftest.py`
- Тест: `backend/core/tests/test_settings.py`

**Интерфейсы:**
- Отдаёт: поля `Settings` — `access_token_ttl_minutes: int`, `refresh_token_ttl_days: int`, `admin_telegram_ids: tuple[int, ...]`, `email_sender: Literal["smtp", "log"]`, `smtp_host: str`, `smtp_port: int`, `smtp_username: str`, `smtp_password: SecretStr`, `smtp_from: str`, `smtp_starttls: bool`.

- [ ] **Шаг 1: Написать падающий тест**

Добавить в `backend/core/tests/test_settings.py`:

```python
def test_admin_ids_parse_from_comma_separated_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """Список админов задаётся строкой: JSON в .env читать неудобно человеку."""
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "111, 222")
    get_settings.cache_clear()

    assert get_settings().admin_telegram_ids == (111, 222)


def test_admin_ids_default_to_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMIN_TELEGRAM_IDS", raising=False)
    get_settings.cache_clear()

    assert get_settings().admin_telegram_ids == ()


def test_token_lifetimes_have_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ACCESS_TOKEN_TTL_MINUTES", raising=False)
    monkeypatch.delenv("REFRESH_TOKEN_TTL_DAYS", raising=False)
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.access_token_ttl_minutes == 15
    assert settings.refresh_token_ttl_days == 30
```

В конце файла добавить фикстуру-автосброс, если её ещё нет:

```python
@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    """Настройки кэшируются на процесс, а тесты меняют окружение."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_settings.py -v`
Expected: FAIL — `Settings object has no attribute admin_telegram_ids`.

- [ ] **Шаг 3: Добавить поля в `Settings`**

В `settings.py` после блока `jwt_secret`/`encryption_key`:

```python
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    # Список идентификаторов Telegram. Роль поднимается при входе; удаление
    # идентификатора отсюда роль не снимает — понижение делается осознанно.
    # NoDecode отключает попытку pydantic-settings разобрать значение как JSON:
    # без неё строка "111, 222" падает с ошибкой парсинга раньше, чем успевает
    # отработать валидатор ниже.
    admin_telegram_ids: Annotated[tuple[int, ...], NoDecode] = ()

    email_sender: Literal["smtp", "log"] = "log"
    smtp_host: str = ""
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = "no-reply@example.org"
    smtp_starttls: bool = False

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def _split_admin_ids(cls, value: object) -> object:
        """Читает "111, 222" из окружения.

        Pydantic ждёт для кортежа JSON-массив, а в .env человек пишет список
        через запятую. Пустая строка означает «админов нет».
        """
        if not isinstance(value, str):
            return value
        return tuple(int(part) for part in value.split(",") if part.strip())
```

- [ ] **Шаг 4: Убедиться, что тесты проходят**

Run: `uv run pytest backend/core/tests/test_settings.py -v`
Expected: PASS.

- [ ] **Шаг 5: Дописать окружение и compose**

В `.env.example` после блока секретов:

```bash
# --- Сессии ---
ACCESS_TOKEN_TTL_MINUTES=15
REFRESH_TOKEN_TTL_DAYS=30

# --- Роли ---
# Идентификаторы Telegram админов через запятую. Роль поднимается при входе,
# факт пишется в audit_log. Свой ID можно узнать у @userinfobot.
ADMIN_TELEGRAM_IDS=

# --- Почта ---
# log — письма только в журнал (локальная разработка без SMTP).
# smtp — реальная отправка. Локально удобно поднять Mailpit:
#   docker compose --profile dev up -d mailpit
#   EMAIL_SENDER=smtp, SMTP_HOST=mailpit, SMTP_PORT=1025, письма на http://localhost:8025
EMAIL_SENDER=log
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=no-reply@example.org
SMTP_STARTTLS=true
```

В `compose.yml` добавить сервис перед `nginx`:

```yaml
  # Только для разработки и сквозных тестов: SMTP-приёмник с веб-интерфейсом.
  # Профиль dev означает, что обычный `docker compose up` его не поднимает.
  mailpit:
    image: axllent/mailpit:latest
    profiles: [dev]
    ports: ["8025:8025"]
    restart: unless-stopped
```

В `conftest.py` в `_TEST_ENV` добавить `"ADMIN_TELEGRAM_IDS": ""` и `"EMAIL_SENDER": "log"`.

В `docs/deployment.md` — раздел о почте и админах: какие переменные заполнить, что при `EMAIL_SENDER=log` регистрация работает, но ссылка подтверждения окажется только в журнале контейнера, и что первый админ назначается через `ADMIN_TELEGRAM_IDS` и должен войти через Telegram.

- [ ] **Шаг 6: Проверка и коммит**

Run: `uv run check`

```bash
git add backend/core/src/repibot_core/settings.py backend/core/tests/test_settings.py .env.example compose.yml conftest.py docs/deployment.md
git commit -m "feat: настройки сессий, почты и списка админов"
```

---

## Задача 2: Модели и миграция

**Файлы:**
- Изменить: `backend/core/src/repibot_core/db/models/user.py`, `backend/core/src/repibot_core/db/models/__init__.py`
- Создать: `backend/core/src/repibot_core/db/models/session.py`, `one_time_token.py`, `audit.py`, `outbox.py`
- Создать: `backend/core/src/repibot_core/db/migrations/versions/0002_identity.py`
- Тест: `backend/core/tests/test_migrations.py`

**Интерфейсы:**
- Отдаёт: `User` с полями `email`, `email_verified_at`, `password_hash`, `telegram_id`, `telegram_username`, `name`, `language`, `role`, `status`, `referral_code`, `referred_by_id`, `remnawave_uuid`, `remnawave_short_uuid`; `UserRole`, `UserStatus`, `TokenType` (`StrEnum`); `Session`, `OneTimeToken`, `AuditLog`, `OutboxMessage`.

- [ ] **Шаг 1: Написать падающий тест**

Добавить в `backend/core/tests/test_migrations.py`:

```python
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
        "remnawave_uuid",
        "remnawave_short_uuid",
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
            text("insert into users (email, language, role, status, referral_code) "
                 "values ('a@example.org', 'ru', 'user', 'active', 'CODE1')")
        )
        with pytest.raises(IntegrityError):
            await connection.execute(
                text("insert into users (email, language, role, status, referral_code) "
                     "values ('a@example.org', 'ru', 'user', 'active', 'CODE2')")
            )
```

Импорт наверху файла: `from sqlalchemy.exc import IntegrityError`.

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_migrations.py -v -m docker`
Expected: FAIL — столбца `email` нет.

- [ ] **Шаг 3: Описать модели**

`user.py` целиком:

```python
"""Пользователь: личность, способы входа, роль."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin


class UserRole(StrEnum):
    user = "user"
    support = "support"
    admin = "admin"


class UserStatus(StrEnum):
    active = "active"
    banned = "banned"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Почта и пароль допускают отсутствие: вошедший через Telegram не имеет ни
    # того, ни другого. Аккаунт существует, пока у него есть хотя бы один
    # способ входа — это правило живёт в domain.identity.can_unlink.
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_hash: Mapped[str | None] = mapped_column(String(255))

    # BigInteger: идентификаторы Telegram давно не влезают в 32 бита.
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64))

    name: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str] = mapped_column(String(2), default="ru")
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=True), default=UserRole.user
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status", native_enum=True), default=UserStatus.active
    )

    referral_code: Mapped[str] = mapped_column(String(16), unique=True)
    referred_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    remnawave_uuid: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    remnawave_short_uuid: Mapped[str | None] = mapped_column(String(64))
```

`session.py`:

```python
"""Refresh-сессия браузера.

Первичный ключ — UUID, а не автоинкремент: идентификатор сессии попадает в
access-токен, и подобрать соседний по номеру не должно быть возможно.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin


class Session(TimestampMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_id", "user_id"),)

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # Хеш предыдущего токена вместе с моментом ротации. Приход предыдущего
    # токена позже окна гонки означает утечку, и сессия отзывается целиком.
    previous_token_hash: Mapped[str | None] = mapped_column(String(64))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user_agent: Mapped[str | None] = mapped_column(String(256))
    ip: Mapped[str | None] = mapped_column(String(45))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

`one_time_token.py`:

```python
"""Одноразовые токены: подтверждение почты, сброс пароля, смена почты."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin


class TokenType(StrEnum):
    email_verify = "email_verify"
    password_reset = "password_reset"
    email_change = "email_change"


class OneTimeToken(TimestampMixin, Base):
    __tablename__ = "one_time_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[TokenType] = mapped_column(Enum(TokenType, name="one_time_token_type"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # В базе только хеш: журнал запросов, дамп или доступ к базе не должны
    # давать возможность подтвердить чужую почту.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

`audit.py`:

```python
"""Журнал значимых действий: что произошло, с кем и как выглядело до и после."""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin


class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(45))
```

`outbox.py`:

```python
"""Очередь надёжной доставки.

Сообщение пишется в той же транзакции, что и изменение данных: иначе
существуют оба плохих исхода — письмо о событии, которого не было, и событие,
о котором никто не узнал.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin


class OutboxMessage(TimestampMixin, Base):
    __tablename__ = "outbox"
    __table_args__ = (Index("ix_outbox_pending", "available_at", "processed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

`models/__init__.py` — экспортировать всё новое:

```python
from repibot_core.db.models.audit import AuditLog
from repibot_core.db.models.one_time_token import OneTimeToken, TokenType
from repibot_core.db.models.outbox import OutboxMessage
from repibot_core.db.models.session import Session
from repibot_core.db.models.user import User, UserRole, UserStatus

__all__ = [
    "AuditLog",
    "OneTimeToken",
    "OutboxMessage",
    "Session",
    "TokenType",
    "User",
    "UserRole",
    "UserStatus",
]
```

- [ ] **Шаг 4: Написать миграцию**

`0002_identity.py`. Столбцы `language`, `role`, `status`, `referral_code` объявлены `NOT NULL`, поэтому добавляются с `server_default`; таблица на этот момент пуста, но `server_default` остаётся — вставка в обход ORM (тест, ручной SQL) не должна падать.

```python
"""Идентичность: способы входа, сессии, одноразовые токены, журнал, outbox.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# create_type=False: типы создаются явным вызовом ниже. Без этого флага
# CREATE TABLE и ADD COLUMN пытаются создать тип ещё раз и падают на
# DuplicateObject — Postgres не умеет CREATE TYPE IF NOT EXISTS.
_ROLE = postgresql.ENUM("user", "support", "admin", name="user_role", create_type=False)
_STATUS = postgresql.ENUM("active", "banned", name="user_status", create_type=False)
_TOKEN_TYPE = postgresql.ENUM(
    "email_verify", "password_reset", "email_change", name="one_time_token_type", create_type=False
)


def upgrade() -> None:
    _ROLE.create(op.get_bind())
    _STATUS.create(op.get_bind())
    _TOKEN_TYPE.create(op.get_bind())

    op.add_column("users", sa.Column("email", sa.String(320), nullable=True))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("telegram_id", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("telegram_username", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("name", sa.String(128), nullable=True))
    op.add_column(
        "users", sa.Column("language", sa.String(2), nullable=False, server_default="ru")
    )
    op.add_column("users", sa.Column("role", _ROLE, nullable=False, server_default="user"))
    op.add_column("users", sa.Column("status", _STATUS, nullable=False, server_default="active"))
    op.add_column("users", sa.Column("referral_code", sa.String(16), nullable=False))
    op.add_column("users", sa.Column("referred_by_id", sa.Integer(), nullable=True))
    op.add_column(
        "users", sa.Column("remnawave_uuid", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("users", sa.Column("remnawave_short_uuid", sa.String(64), nullable=True))

    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_unique_constraint("uq_users_telegram_id", "users", ["telegram_id"])
    op.create_unique_constraint("uq_users_referral_code", "users", ["referral_code"])
    op.create_foreign_key(
        "fk_users_referred_by_id_users",
        "users",
        "users",
        ["referred_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("previous_token_hash", sa.String(64), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(256), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "one_time_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", _TOKEN_TYPE, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=True),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_outbox_pending", "outbox", ["available_at", "processed_at"])


def downgrade() -> None:
    op.drop_index("ix_outbox_pending", table_name="outbox")
    op.drop_table("outbox")
    op.drop_table("audit_log")
    op.drop_table("one_time_tokens")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_constraint("fk_users_referred_by_id_users", "users", type_="foreignkey")
    for constraint in ("uq_users_referral_code", "uq_users_telegram_id", "uq_users_email"):
        op.drop_constraint(constraint, "users", type_="unique")
    for column in (
        "remnawave_short_uuid",
        "remnawave_uuid",
        "referred_by_id",
        "referral_code",
        "status",
        "role",
        "language",
        "name",
        "telegram_username",
        "telegram_id",
        "password_hash",
        "email_verified_at",
        "email",
    ):
        op.drop_column("users", column)

    _TOKEN_TYPE.drop(op.get_bind())
    _STATUS.drop(op.get_bind())
    _ROLE.drop(op.get_bind())
```

- [ ] **Шаг 5: Убедиться, что тесты проходят**

Run: `uv run pytest backend/core/tests/test_migrations.py -v -m docker`
Expected: PASS, включая `test_migrations_match_the_models` и `test_migrations_apply_and_rollback`.

Если `compare_metadata` показывает разницу — правится модель или миграция, но не тест. Частая причина: `server_default` есть в миграции и нет в модели.

- [ ] **Шаг 6: Коммит**

```bash
git add backend/core/src/repibot_core/db backend/core/tests/test_migrations.py
git commit -m "feat: схема идентичности — сессии, токены, журнал, outbox"
```

---

## Задача 3: Правила идентичности в домене

**Файлы:**
- Создать: `backend/core/src/repibot_core/domain/identity.py`
- Тест: `backend/core/tests/test_domain_identity.py`

**Интерфейсы:**
- Отдаёт: `normalize_email(raw: str) -> str`; `PasswordPolicyError`; `validate_password(password: str, *, email: str | None) -> None`; `generate_referral_code() -> str`; `generate_link_code() -> str`; `TOKEN_LIFETIMES: dict[TokenType, timedelta]`; `LoginMethods` (dataclass с `has_password: bool`, `has_telegram: bool`, `passkey_count: int`) с методом `count() -> int`; `can_unlink(methods: LoginMethods, method: Literal["password", "telegram", "passkey"]) -> bool`.

- [ ] **Шаг 1: Написать падающий тест**

Создать `backend/core/tests/test_domain_identity.py`:

```python
"""Правила идентичности. Ни базы, ни сети — только арифметика и строки."""

from __future__ import annotations

from datetime import timedelta

import pytest

from repibot_core.db.models import TokenType
from repibot_core.domain.identity import (
    TOKEN_LIFETIMES,
    LoginMethods,
    PasswordPolicyError,
    can_unlink,
    generate_link_code,
    generate_referral_code,
    normalize_email,
    validate_password,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("User@Example.ORG", "user@example.org"),
        ("  user@example.org  ", "user@example.org"),
    ],
)
def test_email_is_normalized(raw: str, expected: str) -> None:
    assert normalize_email(raw) == expected


def test_password_shorter_than_ten_is_rejected() -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password("short1234", email=None)


def test_password_equal_to_email_is_rejected() -> None:
    """Пароль, равный адресу, ломает единственную защиту при утечке базы."""
    with pytest.raises(PasswordPolicyError):
        validate_password("user@example.org", email="user@example.org")


def test_long_password_is_accepted() -> None:
    validate_password("совершенно обычный пароль", email="user@example.org")


def test_referral_code_avoids_confusable_characters() -> None:
    """Код диктуют голосом и переписывают руками: 0/O и 1/I/L там не место."""
    code = generate_referral_code()

    assert len(code) == 8
    assert set(code) <= set("ABCDEFGHJKMNPQRSTUVWXYZ23456789")


def test_codes_are_not_repeated() -> None:
    assert len({generate_referral_code() for _ in range(50)}) == 50
    assert len({generate_link_code() for _ in range(50)}) == 50


def test_token_lifetimes_match_the_spec() -> None:
    assert TOKEN_LIFETIMES[TokenType.email_verify] == timedelta(hours=24)
    assert TOKEN_LIFETIMES[TokenType.password_reset] == timedelta(hours=1)
    assert TOKEN_LIFETIMES[TokenType.email_change] == timedelta(hours=1)


def test_last_login_method_cannot_be_unlinked() -> None:
    only_telegram = LoginMethods(has_password=False, has_telegram=True, passkey_count=0)

    assert can_unlink(only_telegram, "telegram") is False


def test_method_can_be_unlinked_when_another_remains() -> None:
    both = LoginMethods(has_password=True, has_telegram=True, passkey_count=0)

    assert can_unlink(both, "telegram") is True
    assert can_unlink(both, "password") is True


def test_last_passkey_cannot_be_unlinked_without_password() -> None:
    single_passkey = LoginMethods(has_password=False, has_telegram=False, passkey_count=1)

    assert can_unlink(single_passkey, "passkey") is False
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_domain_identity.py -v`
Expected: FAIL — модуля `repibot_core.domain.identity` нет.

- [ ] **Шаг 3: Реализовать правила**

```python
"""Правила идентичности: почта, пароль, коды, сроки, отвязка способов входа.

Чистые функции без ввода-вывода. Всё, что здесь описано, проверяется тестами
без базы и сети — поэтому сюда и вынесено.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from repibot_core.db.models import TokenType

MIN_PASSWORD_LENGTH = 10

# Без 0/O, 1/I/L: код читают вслух и переписывают руками.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
REFERRAL_CODE_LENGTH = 8
LINK_CODE_LENGTH = 6

TOKEN_LIFETIMES: dict[TokenType, timedelta] = {
    TokenType.email_verify: timedelta(hours=24),
    TokenType.password_reset: timedelta(hours=1),
    TokenType.email_change: timedelta(hours=1),
}

LoginMethod = Literal["password", "telegram", "passkey"]


class PasswordPolicyError(ValueError):
    """Пароль не удовлетворяет требованиям."""


def normalize_email(raw: str) -> str:
    """Приводит адрес к каноническому виду.

    Регистр домена и локальной части для нас не значим, а хранение двух записей
    для одного человека значимо: адрес — уникальный ключ.
    """
    return raw.strip().lower()


def validate_password(password: str, *, email: str | None) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        msg = f"пароль короче {MIN_PASSWORD_LENGTH} символов"
        raise PasswordPolicyError(msg)
    if email is not None and password.strip().lower() == normalize_email(email):
        msg = "пароль совпадает с адресом почты"
        raise PasswordPolicyError(msg)


def _code(length: int) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def generate_referral_code() -> str:
    return _code(REFERRAL_CODE_LENGTH)


def generate_link_code() -> str:
    return _code(LINK_CODE_LENGTH)


@dataclass(frozen=True, slots=True)
class LoginMethods:
    """Способы, которыми пользователь может войти прямо сейчас."""

    has_password: bool
    has_telegram: bool
    passkey_count: int

    def count(self) -> int:
        return int(self.has_password) + int(self.has_telegram) + self.passkey_count


def can_unlink(methods: LoginMethods, method: LoginMethod) -> bool:
    """Можно ли снять способ входа, не заперев человека снаружи.

    Считаем не «сколько способов есть», а «сколько останется»: снятие пароля
    при двух passkey допустимо, снятие единственного Telegram — нет.
    """
    remaining = methods.count()
    if method == "password":
        remaining -= int(methods.has_password)
    elif method == "telegram":
        remaining -= int(methods.has_telegram)
    else:
        remaining -= 1 if methods.passkey_count else 0
    return remaining > 0
```

- [ ] **Шаг 4: Убедиться, что тесты проходят**

Run: `uv run pytest backend/core/tests/test_domain_identity.py -v`
Expected: PASS (11 тестов).

- [ ] **Шаг 5: Коммит**

```bash
git add backend/core/src/repibot_core/domain/identity.py backend/core/tests/test_domain_identity.py
git commit -m "feat: правила идентичности в домене"
```

---

## Задача 4: Пароли и токены

**Файлы:**
- Создать: `backend/core/src/repibot_core/security/__init__.py`, `passwords.py`, `tokens.py`
- Изменить: `backend/core/pyproject.toml` (зависимости `argon2-cffi`, `pyjwt`)
- Тест: `backend/core/tests/test_security.py`

**Интерфейсы:**
- Отдаёт: `hash_password(raw: str) -> str`; `verify_password(stored: str | None, raw: str) -> bool`; `AccessClaims` (dataclass: `user_id: int`, `session_id: UUID`); `create_access_token(user_id: int, session_id: UUID, *, secret: str, ttl_minutes: int, now: datetime | None = None) -> str`; `decode_access_token(token: str, *, secret: str) -> AccessClaims`; `TokenInvalidError`; `generate_opaque_token() -> str`; `hash_opaque_token(raw: str) -> str`.

- [ ] **Шаг 1: Написать падающий тест**

```python
"""Хеширование паролей и работа с токенами."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from repibot_core.security.passwords import hash_password, verify_password
from repibot_core.security.tokens import (
    TokenInvalidError,
    create_access_token,
    decode_access_token,
    generate_opaque_token,
    hash_opaque_token,
)

SECRET = "test-secret"


def test_password_round_trip() -> None:
    stored = hash_password("совершенно обычный пароль")

    assert stored != "совершенно обычный пароль"
    assert verify_password(stored, "совершенно обычный пароль") is True
    assert verify_password(stored, "другой пароль") is False


def test_verify_password_handles_missing_hash() -> None:
    """У вошедшего через Telegram пароля нет.

    Проверка обязана вернуть False, а не упасть — иначе форма входа отвечает
    500 и заодно сообщает, что такой аккаунт существует.
    """
    assert verify_password(None, "любой пароль") is False


def test_access_token_round_trip() -> None:
    session_id = uuid4()

    token = create_access_token(42, session_id, secret=SECRET, ttl_minutes=15)
    claims = decode_access_token(token, secret=SECRET)

    assert claims.user_id == 42
    assert claims.session_id == session_id


def test_expired_access_token_is_rejected() -> None:
    token = create_access_token(
        42,
        uuid4(),
        secret=SECRET,
        ttl_minutes=15,
        now=datetime.now(UTC) - timedelta(hours=1),
    )

    with pytest.raises(TokenInvalidError):
        decode_access_token(token, secret=SECRET)


def test_token_signed_with_another_secret_is_rejected() -> None:
    token = create_access_token(42, uuid4(), secret="чужой секрет", ttl_minutes=15)

    with pytest.raises(TokenInvalidError):
        decode_access_token(token, secret=SECRET)


def test_garbage_is_rejected() -> None:
    with pytest.raises(TokenInvalidError):
        decode_access_token("не токен вовсе", secret=SECRET)


def test_opaque_tokens_are_unique_and_hashed() -> None:
    tokens = {generate_opaque_token() for _ in range(20)}

    assert len(tokens) == 20
    sample = tokens.pop()
    assert hash_opaque_token(sample) == hash_opaque_token(sample)
    assert len(hash_opaque_token(sample)) == 64
    assert hash_opaque_token(sample) != sample
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_security.py -v`
Expected: FAIL — пакета `repibot_core.security` нет.

- [ ] **Шаг 3: Добавить зависимости**

В `backend/core/pyproject.toml` в `dependencies` добавить `"argon2-cffi>=23.1"` и `"pyjwt>=2.10"`. Затем `uv sync`.

- [ ] **Шаг 4: Реализовать пароли**

`passwords.py`:

```python
"""Argon2id. Параметры — библиотечные значения по умолчанию.

Свои значения имеет смысл подбирать под конкретное железо; пока их нет,
библиотечные лучше выдуманных.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, VerifyMismatchError

_hasher = PasswordHasher()

# Хеш заведомо недостижимого пароля. Нужен, чтобы вход по неизвестному адресу
# занимал столько же времени, сколько вход с неверным паролем: иначе время
# ответа сообщает, зарегистрирован ли адрес.
DUMMY_HASH = _hasher.hash("несуществующий пароль для выравнивания времени")


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(stored: str | None, raw: str) -> bool:
    """Сверяет пароль. Отсутствующий хеш — это False, а не исключение."""
    try:
        return _hasher.verify(stored if stored is not None else DUMMY_HASH, raw)
    except (VerifyMismatchError, Argon2Error):
        return False


def needs_rehash(stored: str) -> bool:
    """Параметры Argon2 со временем растут; хеш пересчитывается при входе."""
    return _hasher.check_needs_rehash(stored)
```

- [ ] **Шаг 5: Реализовать токены**

`tokens.py`:

```python
"""Токены: короткий подписанный access и непрозрачный refresh.

В access-токене только идентификатор пользователя и идентификатор сессии.
Роли в нём нет намеренно: она читается из базы через кэш, иначе блокировка
пользователя начинала бы действовать через время жизни токена.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

ALGORITHM = "HS256"
OPAQUE_TOKEN_BYTES = 32


class TokenInvalidError(Exception):
    """Токен просрочен, подделан или не разбирается."""


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: int
    session_id: UUID


def create_access_token(
    user_id: int,
    session_id: UUID,
    *,
    secret: str,
    ttl_minutes: int,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, *, secret: str) -> AccessClaims:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return AccessClaims(user_id=int(payload["sub"]), session_id=UUID(payload["sid"]))
    except (jwt.PyJWTError, KeyError, ValueError) as error:
        raise TokenInvalidError(str(error)) from error


def generate_opaque_token() -> str:
    """Refresh-токен и одноразовые токены из писем.

    Непрозрачный, а не подписанный: такой токен отзывается вычёркиванием из
    базы, а подписанный живёт до истечения срока независимо от нашего желания.
    """
    return secrets.token_urlsafe(OPAQUE_TOKEN_BYTES)


def hash_opaque_token(raw: str) -> str:
    """SHA-256 без соли.

    Соль здесь не нужна и вредна: токен — 256 бит случайности, перебор
    невозможен, а поиск по базе должен идти по индексу одним запросом.
    """
    return hashlib.sha256(raw.encode()).hexdigest()
```

- [ ] **Шаг 6: Убедиться, что тесты проходят**

Run: `uv run pytest backend/core/tests/test_security.py -v`
Expected: PASS (7 тестов).

- [ ] **Шаг 7: Коммит**

```bash
git add backend/core/src/repibot_core/security backend/core/tests/test_security.py backend/core/pyproject.toml uv.lock
git commit -m "feat: хеширование паролей и выдача токенов"
```

---

## Задача 5: Репозитории

**Файлы:**
- Создать: `backend/core/src/repibot_core/db/repositories/__init__.py`, `users.py`, `sessions.py`, `tokens.py`, `outbox.py`, `audit.py`
- Тест: `backend/core/tests/test_repositories.py`
- Изменить: `conftest.py` (фикстура сессии с применёнными миграциями)

**Интерфейсы:**
- Отдаёт: `UserRepository` с `get(id)`, `get_by_email(email)`, `get_by_telegram_id(telegram_id)`, `create(**fields) -> User`, `next_referral_code() -> str`; `SessionRepository` с `create(user_id, token_hash, expires_at, user_agent, ip) -> Session`, `get(session_id)`, `find_by_token_hash(token_hash)`, `find_by_previous_hash(token_hash)`, `rotate(session, new_hash)`, `revoke(session)`, `revoke_all(user_id, except_id=None) -> list[UUID]`, `list_active(user_id)`; `TokenRepository` с `create(type, user_id, token_hash, expires_at, payload=None)`, `find_usable(type, token_hash, now)`, `mark_used(token)`, `invalidate_all(type, user_id)`; `OutboxRepository` с `add(topic, payload, available_at=None)`, `take_batch(limit, now)`, `mark_processed(message)`, `postpone(message, error, delay)`; `AuditRepository` с `record(action, entity, *, actor_id=None, entity_id=None, before=None, after=None, ip=None)`.
- Все методы принимают `AsyncSession` в конструкторе репозитория и не вызывают `commit` — транзакцией владеет сервис.

- [ ] **Шаг 1: Добавить фикстуру базы с миграциями**

В `conftest.py` после фикстуры `engine`:

```python
@pytest_asyncio.fixture
async def db_session(postgres_url: str, engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Чистая база с применёнными миграциями и открытой сессией.

    Схема пересоздаётся на каждый тест: остатки чужих строк дают тесты,
    проходящие по одному и падающие в наборе.
    """
    from alembic import command
    from alembic.config import Config

    from repibot_core.db.engine import create_session_factory

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", postgres_url.replace("+asyncpg", "+psycopg"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    factory = create_session_factory(engine)
    async with factory() as session:
        yield session
```

Добавить импорт `AsyncSession` в блок импортов после подготовки окружения.

- [ ] **Шаг 2: Написать падающий тест**

Создать `backend/core/tests/test_repositories.py`:

```python
"""Репозитории: доступ к данным без бизнес-правил."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import TokenType
from repibot_core.db.repositories.audit import AuditRepository
from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.db.repositories.sessions import SessionRepository
from repibot_core.db.repositories.tokens import TokenRepository
from repibot_core.db.repositories.users import UserRepository

pytestmark = pytest.mark.docker


async def _user(session: AsyncSession, email: str = "user@example.org") -> int:
    users = UserRepository(session)
    user = await users.create(email=email, referral_code=await users.next_referral_code())
    await session.commit()
    return user.id


async def test_user_is_found_by_normalized_email(db_session: AsyncSession) -> None:
    await _user(db_session, "user@example.org")

    found = await UserRepository(db_session).get_by_email("user@example.org")

    assert found is not None
    assert found.email == "user@example.org"


async def test_referral_code_is_unique_across_users(db_session: AsyncSession) -> None:
    users = UserRepository(db_session)
    first = await users.next_referral_code()
    await users.create(email="a@example.org", referral_code=first)
    await db_session.commit()

    assert await users.next_referral_code() != first


async def test_session_rotation_keeps_previous_hash(db_session: AsyncSession) -> None:
    user_id = await _user(db_session)
    sessions = SessionRepository(db_session)
    created = await sessions.create(
        user_id=user_id,
        token_hash="a" * 64,
        expires_at=datetime.now(UTC) + timedelta(days=30),
        user_agent="pytest",
        ip="127.0.0.1",
    )
    await db_session.commit()

    await sessions.rotate(created, "b" * 64)
    await db_session.commit()

    assert created.refresh_token_hash == "b" * 64
    assert created.previous_token_hash == "a" * 64
    assert created.rotated_at is not None
    assert await sessions.find_by_previous_hash("a" * 64) is not None


async def test_revoke_all_keeps_current_session(db_session: AsyncSession) -> None:
    user_id = await _user(db_session)
    sessions = SessionRepository(db_session)
    keep = await sessions.create(
        user_id=user_id,
        token_hash="c" * 64,
        expires_at=datetime.now(UTC) + timedelta(days=30),
        user_agent=None,
        ip=None,
    )
    await sessions.create(
        user_id=user_id,
        token_hash="d" * 64,
        expires_at=datetime.now(UTC) + timedelta(days=30),
        user_agent=None,
        ip=None,
    )
    await db_session.commit()

    revoked = await sessions.revoke_all(user_id, except_id=keep.id)
    await db_session.commit()

    assert len(revoked) == 1
    assert keep.id not in revoked
    assert [item.id for item in await sessions.list_active(user_id)] == [keep.id]


async def test_expired_token_is_not_usable(db_session: AsyncSession) -> None:
    user_id = await _user(db_session)
    tokens = TokenRepository(db_session)
    await tokens.create(
        type=TokenType.email_verify,
        user_id=user_id,
        token_hash="e" * 64,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    await db_session.commit()

    found = await tokens.find_usable(TokenType.email_verify, "e" * 64, datetime.now(UTC))

    assert found is None


async def test_used_token_is_not_usable_twice(db_session: AsyncSession) -> None:
    user_id = await _user(db_session)
    tokens = TokenRepository(db_session)
    token = await tokens.create(
        type=TokenType.password_reset,
        user_id=user_id,
        token_hash="f" * 64,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await db_session.commit()

    await tokens.mark_used(token)
    await db_session.commit()

    assert await tokens.find_usable(TokenType.password_reset, "f" * 64, datetime.now(UTC)) is None


async def test_outbox_batch_skips_postponed_messages(db_session: AsyncSession) -> None:
    outbox = OutboxRepository(db_session)
    ready = await outbox.add("email.verify", {"to": "a@example.org"})
    later = await outbox.add(
        "email.verify",
        {"to": "b@example.org"},
        available_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    await db_session.commit()

    batch = await outbox.take_batch(limit=10, now=datetime.now(UTC))

    assert [item.id for item in batch] == [ready.id]
    assert later.id not in [item.id for item in batch]


async def test_processed_message_is_not_taken_again(db_session: AsyncSession) -> None:
    outbox = OutboxRepository(db_session)
    message = await outbox.add("email.verify", {"to": "a@example.org"})
    await db_session.commit()

    await outbox.mark_processed(message)
    await db_session.commit()

    assert await outbox.take_batch(limit=10, now=datetime.now(UTC)) == []


async def test_audit_record_is_written(db_session: AsyncSession) -> None:
    user_id = await _user(db_session)

    await AuditRepository(db_session).record(
        "role.granted", "user", actor_id=None, entity_id=str(user_id), after={"role": "admin"}
    )
    await db_session.commit()
```

- [ ] **Шаг 3: Убедиться, что тесты падают**

Run: `uv run pytest backend/core/tests/test_repositories.py -v -m docker`
Expected: FAIL — пакета `repositories` нет.

- [ ] **Шаг 4: Реализовать репозитории**

`users.py`:

```python
"""Доступ к пользователям."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.domain.identity import generate_referral_code, normalize_email


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == normalize_email(email))
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        statement = select(User).where(User.telegram_id == telegram_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def create(self, **fields: Any) -> User:
        if "email" in fields and fields["email"] is not None:
            fields["email"] = normalize_email(fields["email"])
        user = User(**fields)
        self._session.add(user)
        await self._session.flush()
        return user

    async def next_referral_code(self) -> str:
        """Подбирает свободный код.

        Уникальность держит ограничение в базе; здесь просто уменьшается
        вероятность нарваться на него. Пять попыток при алфавите из 31 символа
        и восьми знаках — с запасом.
        """
        for _ in range(5):
            code = generate_referral_code()
            statement = select(User.id).where(User.referral_code == code)
            if (await self._session.execute(statement)).first() is None:
                return code
        msg = "не удалось подобрать свободный реферальный код"
        raise RuntimeError(msg)
```

`sessions.py`:

```python
"""Доступ к сессиям."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Session


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
        ip: str | None,
    ) -> Session:
        item = Session(
            user_id=user_id,
            refresh_token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip=ip,
        )
        self._session.add(item)
        await self._session.flush()
        return item

    async def get(self, session_id: UUID) -> Session | None:
        return await self._session.get(Session, session_id)

    async def find_by_token_hash(self, token_hash: str) -> Session | None:
        statement = select(Session).where(Session.refresh_token_hash == token_hash)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def find_by_previous_hash(self, token_hash: str) -> Session | None:
        statement = select(Session).where(Session.previous_token_hash == token_hash)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def rotate(self, item: Session, new_hash: str) -> None:
        item.previous_token_hash = item.refresh_token_hash
        item.refresh_token_hash = new_hash
        item.rotated_at = datetime.now(UTC)
        await self._session.flush()

    async def revoke(self, item: Session) -> None:
        item.revoked_at = datetime.now(UTC)
        await self._session.flush()

    async def revoke_all(self, user_id: int, *, except_id: UUID | None = None) -> list[UUID]:
        """Отзывает сессии пользователя и возвращает идентификаторы отозванных.

        Идентификаторы нужны вызывающему: по ним access-токены помечаются
        недействительными в Valkey, иначе отзыв подействует только через
        время жизни access-токена.
        """
        statement = select(Session).where(
            Session.user_id == user_id, Session.revoked_at.is_(None)
        )
        revoked: list[UUID] = []
        for item in (await self._session.execute(statement)).scalars():
            if except_id is not None and item.id == except_id:
                continue
            item.revoked_at = datetime.now(UTC)
            revoked.append(item.id)
        await self._session.flush()
        return revoked

    async def list_active(self, user_id: int) -> list[Session]:
        statement = (
            select(Session)
            .where(
                Session.user_id == user_id,
                Session.revoked_at.is_(None),
                Session.expires_at > datetime.now(UTC),
            )
            .order_by(Session.created_at.desc())
        )
        return list((await self._session.execute(statement)).scalars())
```

`tokens.py`:

```python
"""Доступ к одноразовым токенам."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import OneTimeToken, TokenType


class TokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        type: TokenType,  # noqa: A002 — имя поля модели, менять его дороже
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        payload: dict[str, Any] | None = None,
    ) -> OneTimeToken:
        token = OneTimeToken(
            type=type,
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            payload=payload,
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def find_usable(
        self, type: TokenType, token_hash: str, now: datetime  # noqa: A002
    ) -> OneTimeToken | None:
        statement = select(OneTimeToken).where(
            OneTimeToken.type == type,
            OneTimeToken.token_hash == token_hash,
            OneTimeToken.used_at.is_(None),
            OneTimeToken.expires_at > now,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def mark_used(self, token: OneTimeToken) -> None:
        token.used_at = datetime.now(UTC)
        await self._session.flush()

    async def invalidate_all(self, type: TokenType, user_id: int) -> None:  # noqa: A002
        """Гасит прежние токены того же типа.

        Запрошенный сброс пароля дважды не должен оставлять две рабочие ссылки:
        письмо могло уйти на адрес, к которому доступ уже потерян.
        """
        statement = (
            update(OneTimeToken)
            .where(
                OneTimeToken.type == type,
                OneTimeToken.user_id == user_id,
                OneTimeToken.used_at.is_(None),
            )
            .values(used_at=datetime.now(UTC))
        )
        await self._session.execute(statement)
```

`outbox.py`:

```python
"""Доступ к очереди надёжной доставки."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import OutboxMessage


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self, topic: str, payload: dict[str, Any], *, available_at: datetime | None = None
    ) -> OutboxMessage:
        message = OutboxMessage(topic=topic, payload=payload)
        if available_at is not None:
            message.available_at = available_at
        self._session.add(message)
        await self._session.flush()
        return message

    async def take_batch(self, *, limit: int, now: datetime) -> list[OutboxMessage]:
        """Забирает готовые сообщения, пропуская занятые другим воркером.

        SKIP LOCKED вместо ожидания блокировки: два воркера должны разбирать
        очередь параллельно, а не стоять в очереди друг за другом.
        """
        statement = (
            select(OutboxMessage)
            .where(OutboxMessage.processed_at.is_(None), OutboxMessage.available_at <= now)
            .order_by(OutboxMessage.available_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self._session.execute(statement)).scalars())

    async def mark_processed(self, message: OutboxMessage) -> None:
        message.processed_at = datetime.now(UTC)
        await self._session.flush()

    async def postpone(self, message: OutboxMessage, error: str, delay: timedelta) -> None:
        message.attempts += 1
        message.last_error = error[:1000]
        message.available_at = datetime.now(UTC) + delay
        await self._session.flush()
```

`audit.py`:

```python
"""Запись в журнал действий."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        action: str,
        entity: str,
        *,
        actor_id: int | None = None,
        entity_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        ip: str | None = None,
    ) -> None:
        self._session.add(
            AuditLog(
                actor_id=actor_id,
                action=action,
                entity=entity,
                entity_id=entity_id,
                before=before,
                after=after,
                ip=ip,
            )
        )
        await self._session.flush()
```

- [ ] **Шаг 5: Убедиться, что тесты проходят**

Run: `uv run pytest backend/core/tests/test_repositories.py -v -m docker`
Expected: PASS (9 тестов).

- [ ] **Шаг 6: Коммит**

```bash
git add backend/core/src/repibot_core/db/repositories backend/core/tests/test_repositories.py conftest.py
git commit -m "feat: репозитории идентичности"
```

---

## Задача 6: Очередь и разбор outbox

**Файлы:**
- Создать: `backend/core/src/repibot_core/queue.py`
- Изменить: `backend/worker/src/repibot_worker/broker.py` (реэкспорт из `core`), `backend/worker/src/repibot_worker/tasks.py`
- Создать: `backend/core/src/repibot_core/services/outbox.py`
- Тест: `backend/core/tests/test_outbox_service.py`

**Интерфейсы:**
- Отдаёт: `repibot_core.queue.broker`, `repibot_core.queue.scheduler`; `OutboxDispatcher` с `register(topic, handler)` и `process(session, *, limit=20, now=None) -> int`; `RETRY_DELAYS: tuple[timedelta, ...]`; `MAX_ATTEMPTS: int`; задачу `process_outbox` в `repibot_worker.tasks`.

**Почему брокер переезжает в `core`:** письмо должно уходить сразу после регистрации, а не в следующую минуту по расписанию. Значит `api` обязан уметь пнуть задачу, а зависеть от пакета `repibot_worker` он не должен — брокер это инфраструктура, и её место рядом с базой и настройками. `repibot_worker.broker` остаётся модулем-реэкспортом, поэтому команды в `compose.yml` и `Dockerfile` не меняются.

- [ ] **Шаг 1: Написать падающий тест**

```python
"""Разбор очереди: ретраи, отказы, повторная обработка."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.services.outbox import MAX_ATTEMPTS, RETRY_DELAYS, OutboxDispatcher

pytestmark = pytest.mark.docker


async def test_handler_is_called_and_message_marked(db_session: AsyncSession) -> None:
    calls: list[dict[str, object]] = []
    dispatcher = OutboxDispatcher()
    dispatcher.register("test.topic", lambda payload: calls.append(payload) or None)

    await OutboxRepository(db_session).add("test.topic", {"value": 1})
    await db_session.commit()

    processed = await dispatcher.process(db_session)

    assert processed == 1
    assert calls == [{"value": 1}]
    assert await OutboxRepository(db_session).take_batch(limit=10, now=datetime.now(UTC)) == []


async def test_failed_handler_postpones_with_growing_delay(db_session: AsyncSession) -> None:
    dispatcher = OutboxDispatcher()

    async def failing(payload: dict[str, object]) -> None:
        raise RuntimeError("SMTP недоступен")

    dispatcher.register("test.topic", failing)
    message = await OutboxRepository(db_session).add("test.topic", {})
    await db_session.commit()

    await dispatcher.process(db_session)

    assert message.attempts == 1
    assert message.processed_at is None
    assert message.last_error is not None
    assert message.available_at > datetime.now(UTC)


async def test_message_is_dropped_after_max_attempts(db_session: AsyncSession) -> None:
    """Бесконечно ретраить нельзя: очередь перестанет разбираться вовсе."""
    dispatcher = OutboxDispatcher()

    async def failing(payload: dict[str, object]) -> None:
        raise RuntimeError("адрес не существует")

    dispatcher.register("test.topic", failing)
    message = await OutboxRepository(db_session).add("test.topic", {})
    message.attempts = MAX_ATTEMPTS - 1
    await db_session.commit()

    await dispatcher.process(db_session)

    assert message.processed_at is not None
    assert message.last_error is not None


async def test_unknown_topic_is_postponed_not_lost(db_session: AsyncSession) -> None:
    """Незнакомая тема — это выкат новой версии в момент работы старого воркера."""
    dispatcher = OutboxDispatcher()
    message = await OutboxRepository(db_session).add("unknown.topic", {})
    await db_session.commit()

    await dispatcher.process(db_session)

    assert message.processed_at is None
    assert message.attempts == 1


def test_retry_delays_grow() -> None:
    assert RETRY_DELAYS[0] < RETRY_DELAYS[-1]
    assert len(RETRY_DELAYS) == MAX_ATTEMPTS
    assert RETRY_DELAYS[0] == timedelta(seconds=10)
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_outbox_service.py -v -m docker`
Expected: FAIL — модуля `services.outbox` нет.

- [ ] **Шаг 3: Перенести брокер в `core`**

`backend/core/src/repibot_core/queue.py` — содержимое прежнего `repibot_worker/broker.py` целиком (вместе с комментариями про `socket_timeout=None` и `LabelScheduleSource`), с добавленной первой строкой докстринга:

```python
"""Брокер и планировщик TaskIQ.

Живёт в core, а не в worker: задачу ставит и api — после регистрации письмо
должно уходить сразу, а не в следующую минуту по расписанию. Зависимость
api → worker при этом не появляется.
"""
```

В `backend/core/pyproject.toml` добавить зависимости `"taskiq>=0.11"` и `"taskiq-redis>=1.0"` (сейчас они в `backend/worker`; в worker остаются — он их тоже импортирует).

`backend/worker/src/repibot_worker/broker.py` заменить на реэкспорт:

```python
"""Брокер воркера.

Модуль сохранён ради путей в командах запуска (`repibot_worker.broker:broker`).
Определения переехали в repibot_core.queue — их использует и api.
"""

from repibot_core.queue import broker, scheduler

__all__ = ["broker", "scheduler"]
```

- [ ] **Шаг 4: Реализовать разбор очереди**

`services/outbox.py`:

```python
"""Разбор очереди надёжной доставки.

Диспетчер не знает, что делают обработчики: он отвечает за попытки, задержки
и за то, что сообщение не потеряется и не отправится дважды.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.outbox import OutboxRepository

logger = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[None]]

# Задержки перед попытками. Последняя попытка — примерно через полчаса после
# первой: этого хватает, чтобы переждать перезапуск почтового сервера, и не
# хватает, чтобы очередь превратилась в свалку.
RETRY_DELAYS: tuple[timedelta, ...] = (
    timedelta(seconds=10),
    timedelta(seconds=60),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(minutes=30),
)
MAX_ATTEMPTS = len(RETRY_DELAYS)


class OutboxDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, topic: str, handler: Handler) -> None:
        self._handlers[topic] = handler

    async def process(
        self, session: AsyncSession, *, limit: int = 20, now: datetime | None = None
    ) -> int:
        """Обрабатывает пачку сообщений. Возвращает число доставленных."""
        moment = now or datetime.now(UTC)
        repository = OutboxRepository(session)
        delivered = 0

        for message in await repository.take_batch(limit=limit, now=moment):
            handler = self._handlers.get(message.topic)
            if handler is None:
                # Тема появится после выката новой версии. Сообщение остаётся
                # в очереди: терять его из-за порядка обновления сервисов нельзя.
                await repository.postpone(
                    message, f"нет обработчика для темы {message.topic}", RETRY_DELAYS[0]
                )
                continue

            try:
                await handler(message.payload)
            except Exception as error:  # noqa: BLE001 — очередь не должна падать целиком
                attempt = message.attempts
                if attempt + 1 >= MAX_ATTEMPTS:
                    # Попытки исчерпаны. Сообщение закрывается с сохранённой
                    # ошибкой: висящая вечно строка мешает разбирать остальные.
                    message.last_error = str(error)[:1000]
                    message.attempts = attempt + 1
                    await repository.mark_processed(message)
                    logger.error(
                        "сообщение outbox отброшено после %s попыток", MAX_ATTEMPTS,
                        extra={"topic": message.topic, "outbox_id": message.id},
                    )
                else:
                    await repository.postpone(message, str(error), RETRY_DELAYS[attempt])
                    logger.warning(
                        "сообщение outbox отложено",
                        extra={"topic": message.topic, "outbox_id": message.id},
                    )
                continue

            await repository.mark_processed(message)
            delivered += 1

        await session.commit()
        return delivered
```

Тест регистрирует синхронный `lambda` — диспетчер обязан принимать только корутины, поэтому в первом тесте обработчик тоже переписывается корутиной:

```python
    async def collect(payload: dict[str, object]) -> None:
        calls.append(payload)

    dispatcher.register("test.topic", collect)
```

- [ ] **Шаг 5: Задача разбора очереди**

Задача объявляется в `core`, а не в `worker`: её ставит `api` сразу после регистрации, и импортировать для этого пакет воркера он не должен.

Создать `backend/core/src/repibot_core/tasks.py`:

```python
"""Фоновые задачи, которые ставит не только воркер.

Расписание раз в минуту — страховка на случай, если процесс, поставивший
задачу, умер между коммитом и постановкой. Обычный путь короче: сервис ставит
задачу сразу после коммита, и письмо уходит за секунды.
"""

from __future__ import annotations

from repibot_core.db.engine import create_engine, create_session_factory
from repibot_core.queue import broker
from repibot_core.services.outbox import OutboxDispatcher
from repibot_core.settings import get_settings


@broker.task(schedule=[{"cron": "* * * * *"}])
async def process_outbox() -> dict[str, int]:
    engine = create_engine(get_settings().database_url)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            delivered = await _dispatcher().process(session)
    finally:
        await engine.dispose()

    return {"delivered": delivered}


def _dispatcher() -> OutboxDispatcher:
    """Собирается на каждый прогон.

    Импорт внутри функции разрывает цикл: обработчики писем лежат в services,
    а services импортирует эту же задачу, чтобы её поставить.
    """
    from repibot_core.services.email_dispatch import build_dispatcher

    return build_dispatcher()
```

`build_dispatcher` появится в задаче 7. До неё `_dispatcher` возвращает `OutboxDispatcher()` без импорта — заменить при выполнении задачи 7.

В `backend/worker/src/repibot_worker/tasks.py` оставить `heartbeat` и добавить реэкспорт, чтобы `taskiq worker ... repibot_worker.tasks` видел задачу:

```python
from repibot_core.tasks import process_outbox

__all__ = ["heartbeat", "process_outbox"]
```

- [ ] **Шаг 6: Проверка и коммит**

Run: `uv run pytest backend/core/tests/test_outbox_service.py backend/worker -v -m docker` затем `uv run check`

```bash
git add backend/core/src/repibot_core/queue.py backend/core/src/repibot_core/tasks.py backend/core/src/repibot_core/services/outbox.py backend/core/tests/test_outbox_service.py backend/worker backend/core/pyproject.toml uv.lock
git commit -m "feat: очередь outbox и её разбор воркером"
```

---

## Задача 7: Письма

**Файлы:**
- Создать: `backend/core/src/repibot_core/integrations/email/__init__.py`, `sender.py`, `templates.py`
- Создать: `backend/core/src/repibot_core/i18n.py`
- Создать: `backend/core/src/repibot_core/services/email_dispatch.py`
- Изменить: `backend/worker/src/repibot_worker/tasks.py`, `backend/core/pyproject.toml`
- Тест: `backend/core/tests/test_email.py`

**Интерфейсы:**
- Отдаёт: `EmailMessage` (dataclass: `to: str`, `subject: str`, `text: str`, `html: str`); `EmailSender` (Protocol с `send(message: EmailMessage) -> None`); `SmtpEmailSender`; `LoggingEmailSender` с полем `sent: list[EmailMessage]`; `build_sender(settings) -> EmailSender`; `render_verification(language, link) -> EmailMessage` и родственные `render_password_reset`, `render_email_change`; `translate(language, key, **params) -> str`; `build_dispatcher() -> OutboxDispatcher`; темы `TOPIC_EMAIL_VERIFY = "email.verify"`, `TOPIC_PASSWORD_RESET = "email.password_reset"`, `TOPIC_EMAIL_CHANGE = "email.change"`.

- [ ] **Шаг 1: Написать падающий тест**

```python
"""Письма: шаблоны, выбор языка, доставка через outbox."""

from __future__ import annotations

import pytest

from repibot_core.i18n import translate
from repibot_core.integrations.email.sender import (
    EmailMessage,
    LoggingEmailSender,
    build_sender,
)
from repibot_core.integrations.email.templates import (
    render_email_change,
    render_password_reset,
    render_verification,
)
from repibot_core.settings import Settings


def test_verification_letter_contains_link_in_both_parts() -> None:
    link = "https://example.org/verify-email?token=abc"

    message = render_verification("ru", link=link, to="user@example.org")

    assert link in message.text
    assert link in message.html
    assert message.to == "user@example.org"


def test_letters_differ_by_language() -> None:
    ru = render_verification("ru", link="https://example.org/x", to="a@example.org")
    en = render_verification("en", link="https://example.org/x", to="a@example.org")

    assert ru.subject != en.subject


def test_unknown_language_falls_back_to_russian() -> None:
    assert translate("de", "email.verify.subject") == translate("ru", "email.verify.subject")


def test_reset_and_change_letters_are_distinct() -> None:
    reset = render_password_reset("ru", link="https://example.org/r", to="a@example.org")
    change = render_email_change("ru", link="https://example.org/c", to="b@example.org")

    assert reset.subject != change.subject


async def test_logging_sender_keeps_messages() -> None:
    sender = LoggingEmailSender()

    await sender.send(EmailMessage(to="a@example.org", subject="s", text="t", html="<p>t</p>"))

    assert len(sender.sent) == 1


def test_build_sender_respects_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_SENDER", "log")
    settings = Settings()  # type: ignore[call-arg]

    assert isinstance(build_sender(settings), LoggingEmailSender)


def test_letters_never_contain_raw_token_in_logs() -> None:
    """Ссылка в письме содержит токен; в журнал попадает только адрес.

    Журнал доступен шире, чем почтовый ящик: токен из него позволил бы
    подтвердить чужую почту.
    """
    sender = LoggingEmailSender()

    assert "token" not in sender.describe(
        EmailMessage(to="a@example.org", subject="s", text="https://x/?token=secret", html="")
    )
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_email.py -v`
Expected: FAIL — пакета `integrations.email` нет.

- [ ] **Шаг 3: Добавить зависимости**

В `backend/core/pyproject.toml`: `"aiosmtplib>=3.0"`, `"jinja2>=3.1"`. Затем `uv sync`.

- [ ] **Шаг 4: Серверные словари**

`i18n.py`:

```python
"""Тексты, которые формирует бэкенд: письма и сообщения бота.

Ошибки API здесь не переводятся — они уходят кодом, фразу подбирает фронтенд.
Письмо и сообщение бота переводить больше некому.
"""

from __future__ import annotations

from typing import Any

FALLBACK = "ru"

_MESSAGES: dict[str, dict[str, str]] = {
    "ru": {
        "email.verify.subject": "Подтвердите почту в Re:Pibot",
        "email.verify.body": (
            "Здравствуйте!\n\nЧтобы завершить регистрацию, откройте ссылку:\n{link}\n\n"
            "Ссылка действует сутки. Если вы не регистрировались, письмо можно удалить."
        ),
        "email.password_reset.subject": "Сброс пароля в Re:Pibot",
        "email.password_reset.body": (
            "Чтобы задать новый пароль, откройте ссылку:\n{link}\n\n"
            "Ссылка действует час. Если вы не запрашивали сброс, ничего делать не нужно."
        ),
        "email.change.subject": "Подтвердите новый адрес почты",
        "email.change.body": (
            "Вы указали этот адрес как новый в Re:Pibot. Чтобы подтвердить, откройте ссылку:\n"
            "{link}\n\nСсылка действует час."
        ),
        "bot.start.greeting": "Здравствуйте, {name}. Это Re:Pibot.",
        "bot.start.open_app": "Открыть приложение",
        "bot.language.choose": "Выберите язык",
        "bot.language.saved": "Язык сохранён",
    },
    "en": {
        "email.verify.subject": "Confirm your email for Re:Pibot",
        "email.verify.body": (
            "Hello!\n\nTo finish signing up, open this link:\n{link}\n\n"
            "The link is valid for 24 hours. If you did not sign up, ignore this message."
        ),
        "email.password_reset.subject": "Reset your Re:Pibot password",
        "email.password_reset.body": (
            "To set a new password, open this link:\n{link}\n\n"
            "The link is valid for one hour. If you did not ask for it, no action is needed."
        ),
        "email.change.subject": "Confirm your new email address",
        "email.change.body": (
            "You set this address as your new one in Re:Pibot. To confirm, open this link:\n"
            "{link}\n\nThe link is valid for one hour."
        ),
        "bot.start.greeting": "Hello, {name}. This is Re:Pibot.",
        "bot.start.open_app": "Open the app",
        "bot.language.choose": "Choose a language",
        "bot.language.saved": "Language saved",
    },
}


def translate(language: str, key: str, **params: Any) -> str:
    """Берёт строку для языка, при незнакомом языке — русскую."""
    messages = _MESSAGES.get(language, _MESSAGES[FALLBACK])
    template = messages.get(key) or _MESSAGES[FALLBACK][key]
    return template.format(**params) if params else template
```

- [ ] **Шаг 5: Отправка и шаблоны**

`sender.py`:

```python
"""Отправка писем: интерфейс и две реализации."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from email.message import EmailMessage as MimeMessage
from typing import Protocol

import aiosmtplib

from repibot_core.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


def _describe(message: EmailMessage) -> str:
    """Строка для журнала: адрес и тема, без тела.

    В теле лежит ссылка с токеном подтверждения, а журнал доступен шире, чем
    почтовый ящик получателя.
    """
    return f"письмо «{message.subject}» на {message.to}"


@dataclass
class LoggingEmailSender:
    """Пишет в журнал вместо отправки. Локальная разработка и тесты."""

    sent: list[EmailMessage] = field(default_factory=list)

    def describe(self, message: EmailMessage) -> str:
        return _describe(message)

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)
        # Ссылка нужна разработчику целиком: без неё локально не подтвердить
        # почту. Уровень DEBUG, и в production этот отправитель не используется.
        logger.info("%s (не отправлено, EMAIL_SENDER=log)", _describe(message))
        logger.debug("тело письма: %s", message.text)


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self._settings.smtp_from
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        mime.add_alternative(message.html, subtype="html")

        await aiosmtplib.send(
            mime,
            hostname=self._settings.smtp_host,
            port=self._settings.smtp_port,
            username=self._settings.smtp_username or None,
            password=self._settings.smtp_password.get_secret_value() or None,
            start_tls=self._settings.smtp_starttls,
            timeout=20,
        )
        logger.info("%s отправлено", _describe(message))


def build_sender(settings: Settings) -> EmailSender:
    if settings.email_sender == "smtp":
        return SmtpEmailSender(settings)
    return LoggingEmailSender()
```

`templates.py`:

```python
"""Шаблоны писем.

HTML-часть собирается из одного каркаса: письма различаются текстом, а не
вёрсткой. Цвета — из бренд-бука, значениями, потому что CSS-переменные в
почтовых клиентах не работают.
"""

from __future__ import annotations

from jinja2 import Environment

from repibot_core.i18n import translate
from repibot_core.integrations.email.sender import EmailMessage

INK = "#1A1A18"
PAPER = "#FAF9F7"
JADE = "#17A67C"
# Ссылка — мелкий текст: Jade к белому даёт 3.1:1, и бренд-бук требует для
# текста и ссылок Jade Deep с контрастом 6.6:1. Основной Jade остаётся на
# двоеточии в логотипе — крупный элемент.
JADE_DEEP = "#0E6B50"

_LAYOUT = Environment(autoescape=True).from_string(
    """<!doctype html>
<html lang="{{ language }}">
  <body style="margin:0;padding:24px;background:{{ paper }};color:{{ ink }};
               font-family:-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.5">
    <div style="max-width:520px;margin:0 auto">
      <p style="font-size:20px;font-weight:600;margin:0 0 24px">
        Re<span style="color:{{ jade }}">:</span>Pibot
      </p>
      {% for paragraph in paragraphs %}
        <p style="margin:0 0 16px">{{ paragraph }}</p>
      {% endfor %}
      <p style="margin:24px 0 0">
        <a href="{{ link }}" style="color:{{ jade }}">{{ link }}</a>
      </p>
    </div>
  </body>
</html>
"""
)


def _render(language: str, *, to: str, subject_key: str, body_key: str, link: str) -> EmailMessage:
    text = translate(language, body_key, link=link)
    paragraphs = [line for line in text.split("\n") if line.strip() and link not in line]
    html = _LAYOUT.render(
        language=language, paragraphs=paragraphs, link=link, ink=INK, paper=PAPER, jade=JADE
    )
    return EmailMessage(
        to=to, subject=translate(language, subject_key), text=text, html=html
    )


def render_verification(language: str, *, link: str, to: str) -> EmailMessage:
    return _render(
        language,
        to=to,
        subject_key="email.verify.subject",
        body_key="email.verify.body",
        link=link,
    )


def render_password_reset(language: str, *, link: str, to: str) -> EmailMessage:
    return _render(
        language,
        to=to,
        subject_key="email.password_reset.subject",
        body_key="email.password_reset.body",
        link=link,
    )


def render_email_change(language: str, *, link: str, to: str) -> EmailMessage:
    return _render(
        language,
        to=to,
        subject_key="email.change.subject",
        body_key="email.change.body",
        link=link,
    )
```

- [ ] **Шаг 6: Связать очередь с письмами**

`services/email_dispatch.py`:

```python
"""Обработчики почтовых тем очереди.

Полезная нагрузка сообщения содержит только язык, адрес и ссылку. Ни токена
отдельно, ни идентификатора пользователя: обработчик не должен уметь ничего
кроме отправки того, что ему передали.
"""

from __future__ import annotations

from typing import Any

from repibot_core.integrations.email.sender import EmailSender, build_sender
from repibot_core.integrations.email.templates import (
    render_email_change,
    render_password_reset,
    render_verification,
)
from repibot_core.services.outbox import OutboxDispatcher
from repibot_core.settings import get_settings

TOPIC_EMAIL_VERIFY = "email.verify"
TOPIC_PASSWORD_RESET = "email.password_reset"
TOPIC_EMAIL_CHANGE = "email.change"

_RENDERERS = {
    TOPIC_EMAIL_VERIFY: render_verification,
    TOPIC_PASSWORD_RESET: render_password_reset,
    TOPIC_EMAIL_CHANGE: render_email_change,
}


def build_dispatcher(sender: EmailSender | None = None) -> OutboxDispatcher:
    """Собирает диспетчер с почтовыми темами.

    Отправитель принимается параметром, чтобы тест подставил свой без правки
    настроек окружения.
    """
    resolved = sender if sender is not None else build_sender(get_settings())
    dispatcher = OutboxDispatcher()

    for topic, renderer in _RENDERERS.items():

        async def handle(payload: dict[str, Any], renderer=renderer) -> None:  # type: ignore[no-untyped-def]
            message = renderer(
                payload["language"], link=payload["link"], to=payload["to"]
            )
            await resolved.send(message)

        dispatcher.register(topic, handle)

    return dispatcher
```

Заменить `OutboxDispatcher()` на `build_dispatcher()` в `repibot_worker/tasks.py` и добавить импорт.

- [ ] **Шаг 7: Тест сквозного пути очереди**

Добавить в `backend/core/tests/test_email.py`:

```python
@pytest.mark.docker
async def test_queued_letter_is_delivered(db_session: AsyncSession) -> None:
    sender = LoggingEmailSender()
    await OutboxRepository(db_session).add(
        TOPIC_EMAIL_VERIFY,
        {"language": "ru", "to": "user@example.org", "link": "https://example.org/v?token=x"},
    )
    await db_session.commit()

    delivered = await build_dispatcher(sender).process(db_session)

    assert delivered == 1
    assert sender.sent[0].to == "user@example.org"
```

- [ ] **Шаг 8: Проверка и коммит**

Run: `uv run pytest backend/core/tests/test_email.py -v` затем `uv run check`

```bash
git add backend/core/src/repibot_core/i18n.py backend/core/src/repibot_core/integrations/email backend/core/src/repibot_core/services/email_dispatch.py backend/core/tests/test_email.py backend/worker/src/repibot_worker/tasks.py backend/core/pyproject.toml uv.lock
git commit -m "feat: письма подтверждения, сброса и смены адреса"
```

---

## Задача 8: Кэш роли и отзыв сессий

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/principal.py`
- Изменить: `pyproject.toml` (dev-зависимость `fakeredis`)
- Тест: `backend/core/tests/test_principal.py`

**Интерфейсы:**
- Отдаёт: `Principal` (dataclass: `user_id: int`, `role: UserRole`, `status: UserStatus`, `language: str`); `PrincipalCache(redis, ttl_seconds=30)` с методами `get(session, user_id) -> Principal | None`, `invalidate(user_id)`, `mark_session_revoked(session_id, ttl_seconds)`, `is_session_revoked(session_id) -> bool`.

- [ ] **Шаг 1: Написать падающий тест**

```python
"""Кэш роли и статуса, отметки отозванных сессий."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import UserRole, UserStatus
from repibot_core.db.repositories.users import UserRepository
from repibot_core.services.principal import PrincipalCache

pytestmark = pytest.mark.docker


async def test_principal_is_read_from_database_then_cached(db_session: AsyncSession) -> None:
    users = UserRepository(db_session)
    user = await users.create(email="a@example.org", referral_code=await users.next_referral_code())
    await db_session.commit()
    cache = PrincipalCache(FakeRedis())

    first = await cache.get(db_session, user.id)
    user.role = UserRole.admin
    await db_session.commit()
    second = await cache.get(db_session, user.id)

    assert first is not None
    assert first.role == UserRole.user
    # Роль изменилась в базе, но кэш ещё жив: это осознанная задержка в 30 секунд.
    assert second is not None
    assert second.role == UserRole.user


async def test_invalidate_makes_change_visible(db_session: AsyncSession) -> None:
    users = UserRepository(db_session)
    user = await users.create(email="b@example.org", referral_code=await users.next_referral_code())
    await db_session.commit()
    cache = PrincipalCache(FakeRedis())
    await cache.get(db_session, user.id)

    user.status = UserStatus.banned
    await db_session.commit()
    await cache.invalidate(user.id)

    principal = await cache.get(db_session, user.id)
    assert principal is not None
    assert principal.status == UserStatus.banned


async def test_missing_user_gives_none(db_session: AsyncSession) -> None:
    cache = PrincipalCache(FakeRedis())

    assert await cache.get(db_session, 999_999) is None


async def test_revoked_session_is_remembered() -> None:
    cache = PrincipalCache(FakeRedis())
    session_id = uuid4()

    assert await cache.is_session_revoked(session_id) is False

    await cache.mark_session_revoked(session_id, ttl_seconds=900)

    assert await cache.is_session_revoked(session_id) is True
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_principal.py -v -m docker`
Expected: FAIL — модуля нет, `fakeredis` не установлен.

- [ ] **Шаг 3: Добавить dev-зависимость**

В корневой `pyproject.toml`, группа `dev`: `"fakeredis>=2.26"`. Затем `uv sync`.

- [ ] **Шаг 4: Реализовать кэш**

```python
"""Кто выполняет запрос: роль, статус, язык.

Роль не лежит в access-токене — иначе блокировка пользователя начинала бы
действовать через время жизни токена. Вместо этого одно чтение из Valkey с
коротким сроком жизни, с проваливанием в базу при промахе.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import UserRole, UserStatus
from repibot_core.db.repositories.users import UserRepository

PRINCIPAL_TTL_SECONDS = 30


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: int
    role: UserRole
    status: UserStatus
    language: str

    @property
    def is_active(self) -> bool:
        return self.status is UserStatus.active


class PrincipalCache:
    def __init__(self, redis: Redis, ttl_seconds: int = PRINCIPAL_TTL_SECONDS) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def _key(user_id: int) -> str:
        return f"principal:{user_id}"

    @staticmethod
    def _revoked_key(session_id: UUID) -> str:
        return f"session:revoked:{session_id}"

    async def get(self, session: AsyncSession, user_id: int) -> Principal | None:
        cached = await self._redis.get(self._key(user_id))
        if cached is not None:
            data = json.loads(cached)
            return Principal(
                user_id=data["user_id"],
                role=UserRole(data["role"]),
                status=UserStatus(data["status"]),
                language=data["language"],
            )

        user = await UserRepository(session).get(user_id)
        if user is None:
            return None

        principal = Principal(
            user_id=user.id, role=user.role, status=user.status, language=user.language
        )
        await self._redis.set(
            self._key(user_id),
            json.dumps(
                {
                    "user_id": principal.user_id,
                    "role": principal.role.value,
                    "status": principal.status.value,
                    "language": principal.language,
                }
            ),
            ex=self._ttl,
        )
        return principal

    async def invalidate(self, user_id: int) -> None:
        await self._redis.delete(self._key(user_id))

    async def mark_session_revoked(self, session_id: UUID, *, ttl_seconds: int) -> None:
        """Помечает сессию отозванной на время жизни выданного access-токена.

        Дольше держать незачем: после истечения токена он не примется и без
        отметки. Без отметки же отзыв сессии подействовал бы только к тому же
        моменту — а критерий приёмки требует немедленности.
        """
        await self._redis.set(self._revoked_key(session_id), "1", ex=ttl_seconds)

    async def is_session_revoked(self, session_id: UUID) -> bool:
        return await self._redis.exists(self._revoked_key(session_id)) == 1
```

- [ ] **Шаг 5: Убедиться, что тесты проходят**

Run: `uv run pytest backend/core/tests/test_principal.py -v -m docker`
Expected: PASS (4 теста).

- [ ] **Шаг 6: Коммит**

```bash
git add backend/core/src/repibot_core/services/principal.py backend/core/tests/test_principal.py pyproject.toml uv.lock
git commit -m "feat: кэш роли и отметки отозванных сессий"
```

---

## Задача 9: AuthService — выдача, обновление и отзыв сессий

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/auth/__init__.py`, `types.py`, `service.py`
- Тест: `backend/core/tests/test_auth_sessions.py`

**Интерфейсы:**
- Отдаёт: `AuthError(Exception)` с полем `code: str`; `IssuedSession` (dataclass: `access_token: str`, `refresh_token: str | None`, `session_id: UUID`, `access_expires_in: int`, `refresh_expires_at: datetime | None`); `AuthService(session, settings, principals)` с методами `issue(user, *, user_agent, ip, with_refresh) -> IssuedSession`, `refresh(raw_token, *, user_agent, ip) -> IssuedSession`, `logout(session_id) -> None`, `revoke_session(user_id, session_id) -> None`, `revoke_other_sessions(user_id, current_id) -> None`.
- Коды ошибок: `token_invalid` — токен не найден, просрочен или сессия отозвана; `forbidden` — пользователь заблокирован.

- [ ] **Шаг 1: Написать падающий тест**

```python
"""Выдача, ротация и отзыв сессий."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User, UserStatus
from repibot_core.db.repositories.sessions import SessionRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.security.tokens import decode_access_token
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError
from repibot_core.services.principal import PrincipalCache
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker


async def _service(session: AsyncSession) -> AuthService:
    return AuthService(session, get_settings(), PrincipalCache(FakeRedis()))


async def _user(session: AsyncSession, **fields: object) -> User:
    users = UserRepository(session)
    user = await users.create(
        email="user@example.org", referral_code=await users.next_referral_code(), **fields
    )
    await session.commit()
    return user


async def test_issue_returns_working_access_token(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    service = await _service(db_session)

    issued = await service.issue(user, user_agent="pytest", ip="127.0.0.1", with_refresh=True)

    claims = decode_access_token(issued.access_token, secret=get_settings().jwt_secret.get_secret_value())
    assert claims.user_id == user.id
    assert claims.session_id == issued.session_id
    assert issued.refresh_token is not None


async def test_miniapp_session_has_no_refresh(db_session: AsyncSession) -> None:
    """В MiniApp cookie не выживает: refresh там не выдаётся вовсе."""
    user = await _user(db_session)
    service = await _service(db_session)

    issued = await service.issue(user, user_agent=None, ip=None, with_refresh=False)

    assert issued.refresh_token is None


async def test_refresh_rotates_token(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    service = await _service(db_session)
    issued = await service.issue(user, user_agent=None, ip=None, with_refresh=True)
    assert issued.refresh_token is not None

    rotated = await service.refresh(issued.refresh_token, user_agent=None, ip=None)

    assert rotated.refresh_token is not None
    assert rotated.refresh_token != issued.refresh_token
    assert rotated.session_id == issued.session_id


async def test_previous_token_works_inside_race_window(db_session: AsyncSession) -> None:
    """Две вкладки обновляют токен одновременно — обе должны остаться в системе."""
    user = await _user(db_session)
    service = await _service(db_session)
    issued = await service.issue(user, user_agent=None, ip=None, with_refresh=True)
    assert issued.refresh_token is not None
    await service.refresh(issued.refresh_token, user_agent=None, ip=None)

    again = await service.refresh(issued.refresh_token, user_agent=None, ip=None)

    assert again.refresh_token is not None


async def test_previous_token_after_window_revokes_session(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    service = await _service(db_session)
    issued = await service.issue(user, user_agent=None, ip=None, with_refresh=True)
    assert issued.refresh_token is not None
    rotated = await service.refresh(issued.refresh_token, user_agent=None, ip=None)

    session_row = await SessionRepository(db_session).get(issued.session_id)
    assert session_row is not None
    session_row.rotated_at = datetime.now(UTC) - timedelta(minutes=5)
    await db_session.commit()

    with pytest.raises(AuthError) as error:
        await service.refresh(issued.refresh_token, user_agent=None, ip=None)

    assert error.value.code == "token_invalid"
    # Утечка означает, что и текущий токен считать своим больше нельзя.
    assert rotated.refresh_token is not None
    with pytest.raises(AuthError):
        await service.refresh(rotated.refresh_token, user_agent=None, ip=None)


async def test_unknown_token_is_rejected(db_session: AsyncSession) -> None:
    service = await _service(db_session)

    with pytest.raises(AuthError) as error:
        await service.refresh("никогда не выдавался", user_agent=None, ip=None)

    assert error.value.code == "token_invalid"


async def test_expired_session_is_rejected(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    service = await _service(db_session)
    issued = await service.issue(user, user_agent=None, ip=None, with_refresh=True)
    assert issued.refresh_token is not None

    row = await SessionRepository(db_session).get(issued.session_id)
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(days=1)
    await db_session.commit()

    with pytest.raises(AuthError):
        await service.refresh(issued.refresh_token, user_agent=None, ip=None)


async def test_banned_user_cannot_refresh(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    service = await _service(db_session)
    issued = await service.issue(user, user_agent=None, ip=None, with_refresh=True)
    assert issued.refresh_token is not None

    user.status = UserStatus.banned
    await db_session.commit()

    with pytest.raises(AuthError) as error:
        await service.refresh(issued.refresh_token, user_agent=None, ip=None)

    assert error.value.code == "forbidden"


async def test_logout_revokes_only_current_session(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    service = await _service(db_session)
    first = await service.issue(user, user_agent=None, ip=None, with_refresh=True)
    second = await service.issue(user, user_agent=None, ip=None, with_refresh=True)

    await service.logout(first.session_id)

    active = [item.id for item in await SessionRepository(db_session).list_active(user.id)]
    assert active == [second.session_id]
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Run: `uv run pytest backend/core/tests/test_auth_sessions.py -v -m docker`
Expected: FAIL — пакета `services.auth` нет.

- [ ] **Шаг 3: Описать типы**

`types.py`:

```python
"""Общие типы способов входа."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


class AuthError(Exception):
    """Ошибка входа, о которой клиенту сообщается кодом.

    Код совпадает с тем, что уходит в теле ответа API: перевод кода в фразу —
    дело фронтенда, а выбор статуса — дело роутера.
    """

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    """Результат работы одного способа входа: кто это.

    Способ входа не выдаёт токенов и не проверяет статус — только опознаёт.
    """

    user_id: int


@dataclass(frozen=True, slots=True)
class IssuedSession:
    access_token: str
    refresh_token: str | None
    session_id: UUID
    access_expires_in: int
    refresh_expires_at: datetime | None
```

- [ ] **Шаг 4: Реализовать сервис**

`service.py`:

```python
"""Единственный путь выдачи сессии.

Любой способ входа заканчивается здесь: проверка статуса, повышение роли по
списку админов, запись в журнал и выдача токенов написаны один раз.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User, UserRole, UserStatus
from repibot_core.db.repositories.audit import AuditRepository
from repibot_core.db.repositories.sessions import SessionRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.security.tokens import (
    create_access_token,
    generate_opaque_token,
    hash_opaque_token,
)
from repibot_core.services.auth.types import AuthError, IssuedSession
from repibot_core.services.principal import PrincipalCache
from repibot_core.settings import Settings

logger = logging.getLogger(__name__)

# Окно, внутри которого приход предыдущего refresh-токена считается гонкой
# вкладок, а не утечкой. Две вкладки, одновременно заметившие истёкший access,
# обновляются с разницей в миллисекунды; злоумышленник с украденной cookie
# приходит заметно позже.
ROTATION_RACE_WINDOW = timedelta(seconds=30)


class AuthService:
    def __init__(
        self, session: AsyncSession, settings: Settings, principals: PrincipalCache
    ) -> None:
        self._session = session
        self._settings = settings
        self._principals = principals
        self._sessions = SessionRepository(session)
        self._users = UserRepository(session)
        self._audit = AuditRepository(session)

    async def issue(
        self,
        user: User,
        *,
        user_agent: str | None,
        ip: str | None,
        with_refresh: bool,
    ) -> IssuedSession:
        if user.status is not UserStatus.active:
            raise AuthError("forbidden", "аккаунт заблокирован")

        await self._promote_if_admin(user, ip=ip)

        raw_refresh = generate_opaque_token() if with_refresh else None
        # Сессия создаётся всегда, даже без refresh: её идентификатор попадает
        # в access-токен, и без него нельзя ни отозвать доступ, ни показать
        # список устройств.
        expires_at = datetime.now(UTC) + timedelta(days=self._settings.refresh_token_ttl_days)
        row = await self._sessions.create(
            user_id=user.id,
            # У сессии без refresh (MiniApp) поле всё равно заполняется: оно
            # NOT NULL и уникально. Значение — хеш от выброшенного случайного
            # токена: предъявить его нельзя, прообраза не знает никто, и в базе
            # оно выглядит хешем, а не испорченной строкой.
            token_hash=hash_opaque_token(raw_refresh or generate_opaque_token()),
            expires_at=expires_at,
            user_agent=(user_agent or None) and user_agent[:256],
            ip=ip,
        )
        await self._session.commit()

        return self._pack(user.id, row.id, raw_refresh, expires_at if raw_refresh else None)

    async def refresh(
        self, raw_token: str, *, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        token_hash = hash_opaque_token(raw_token)
        row = await self._sessions.find_by_token_hash(token_hash)

        if row is None:
            # Токена нет среди текущих. Возможно, это предыдущий — тогда решает
            # окно ротации: гонка вкладок обслуживается, утечка отзывается.
            row = await self._handle_possible_reuse(token_hash)
            if row is None:
                raise AuthError("token_invalid", "токен не найден")

        now = datetime.now(UTC)
        if row.revoked_at is not None or row.expires_at <= now:
            raise AuthError("token_invalid", "сессия недействительна")

        user = await self._users.get(row.user_id)
        if user is None:
            raise AuthError("token_invalid", "пользователь удалён")
        if user.status is not UserStatus.active:
            raise AuthError("forbidden", "аккаунт заблокирован")

        new_raw = generate_opaque_token()
        await self._sessions.rotate(row, hash_opaque_token(new_raw))
        if user_agent:
            row.user_agent = user_agent[:256]
        if ip:
            row.ip = ip
        await self._session.commit()

        return self._pack(row.user_id, row.id, new_raw, row.expires_at)

    async def logout(self, session_id: UUID) -> None:
        row = await self._sessions.get(session_id)
        if row is None or row.revoked_at is not None:
            return
        await self._sessions.revoke(row)
        await self._principals.mark_session_revoked(
            session_id, ttl_seconds=self._settings.access_token_ttl_minutes * 60
        )
        await self._session.commit()

    async def revoke_session(self, user_id: int, session_id: UUID) -> None:
        row = await self._sessions.get(session_id)
        # Чужую сессию отозвать нельзя, и знать о её существовании тоже:
        # ответ одинаков для несуществующей и для принадлежащей другому.
        if row is None or row.user_id != user_id:
            raise AuthError("not_found", "сессия не найдена")
        await self.logout(session_id)

    async def revoke_other_sessions(self, user_id: int, current_id: UUID) -> None:
        revoked = await self._sessions.revoke_all(user_id, except_id=current_id)
        for session_id in revoked:
            await self._principals.mark_session_revoked(
                session_id, ttl_seconds=self._settings.access_token_ttl_minutes * 60
            )
        await self._session.commit()

    async def revoke_all_sessions(self, user_id: int) -> None:
        """Отзывает всё. Используется при смене и сбросе пароля."""
        revoked = await self._sessions.revoke_all(user_id)
        for session_id in revoked:
            await self._principals.mark_session_revoked(
                session_id, ttl_seconds=self._settings.access_token_ttl_minutes * 60
            )
        await self._session.commit()

    async def _handle_possible_reuse(self, token_hash: str) -> Session | None:
        """Разбирает приход предыдущего токена.

        Возвращает сессию, если это гонка вкладок внутри окна — тогда вызывающий
        просто выдаёт новую пару. Возвращает None, если это утечка: сессия
        отзывается целиком, потому что копию токена держит кто-то ещё, и какой
        из двух держателей настоящий, мы не знаем.
        """
        row = await self._sessions.find_by_previous_hash(token_hash)
        if row is None or row.revoked_at is not None:
            return None

        rotated_at = row.rotated_at or row.created_at
        if datetime.now(UTC) - rotated_at <= ROTATION_RACE_WINDOW:
            return row

        await self._sessions.revoke(row)
        await self._principals.mark_session_revoked(
            row.id, ttl_seconds=self._settings.access_token_ttl_minutes * 60
        )
        await self._audit.record(
            "session.reuse_detected", "session", actor_id=row.user_id, entity_id=str(row.id)
        )
        await self._session.commit()
        logger.warning("повторное использование refresh-токена", extra={"session_id": str(row.id)})
        return None

    async def _promote_if_admin(self, user: User, *, ip: str | None) -> None:
        if user.telegram_id is None or user.role is UserRole.admin:
            return
        if user.telegram_id not in self._settings.admin_telegram_ids:
            return

        before = user.role.value
        user.role = UserRole.admin
        await self._audit.record(
            "role.granted",
            "user",
            actor_id=user.id,
            entity_id=str(user.id),
            before={"role": before},
            after={"role": UserRole.admin.value},
            ip=ip,
        )
        await self._principals.invalidate(user.id)
        logger.info("роль admin выдана по списку ADMIN_TELEGRAM_IDS", extra={"user_id": user.id})

    def _pack(
        self,
        user_id: int,
        session_id: UUID,
        raw_refresh: str | None,
        refresh_expires_at: datetime | None,
    ) -> IssuedSession:
        ttl = self._settings.access_token_ttl_minutes
        return IssuedSession(
            access_token=create_access_token(
                user_id,
                session_id,
                secret=self._settings.jwt_secret.get_secret_value(),
                ttl_minutes=ttl,
            ),
            refresh_token=raw_refresh,
            session_id=session_id,
            access_expires_in=ttl * 60,
            refresh_expires_at=refresh_expires_at,
        )
```

Импорт модели сессии для аннотации: `from repibot_core.db.models import Session, User, UserRole, UserStatus`.

- [ ] **Шаг 5: Убедиться, что тесты проходят**

Run: `uv run pytest backend/core/tests/test_auth_sessions.py -v -m docker`
Expected: PASS (9 тестов).

- [ ] **Шаг 6: Коммит**

```bash
git add backend/core/src/repibot_core/services/auth backend/core/tests/test_auth_sessions.py
git commit -m "feat: выдача, ротация и отзыв сессий"
```

---

## Задача 10: Регистрация, подтверждение почты, вход паролем, сброс

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/auth/password.py`
- Тест: `backend/core/tests/test_auth_password.py`

**Интерфейсы:**
- Отдаёт: `PasswordAuth(session, settings, auth: AuthService)` с методами `register(email, password, language) -> None`, `resend_verification(email) -> None`, `verify_email(raw_token, *, user_agent, ip) -> IssuedSession`, `login(email, password, *, user_agent, ip) -> IssuedSession`, `request_reset(email) -> None`, `reset(raw_token, new_password, *, user_agent, ip) -> IssuedSession`.
- Коды ошибок: `email_taken`, `weak_password`, `invalid_credentials`, `email_not_verified`, `token_invalid`.

- [ ] **Шаг 1: Написать падающий тест**

```python
"""Регистрация и вход паролем."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import TokenType
from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.db.repositories.tokens import TokenRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.security.tokens import hash_opaque_token
from repibot_core.services.auth.password import PasswordAuth
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError
from repibot_core.services.email_dispatch import TOPIC_EMAIL_VERIFY
from repibot_core.services.principal import PrincipalCache
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker

PASSWORD = "совершенно обычный пароль"


def _auth(session: AsyncSession) -> PasswordAuth:
    settings = get_settings()
    return PasswordAuth(
        session, settings, AuthService(session, settings, PrincipalCache(FakeRedis()))
    )


async def _token_from_outbox(session: AsyncSession, topic: str) -> str:
    """Достаёт токен из ссылки в поставленном письме.

    Тест ходит тем же путём, что и пользователь: у сервиса нет метода, который
    вернул бы токен напрямую, — иначе он появился бы и в продакшене.
    """
    messages = await OutboxRepository(session).take_batch(limit=10, now=datetime.now(UTC))
    letter = next(item for item in messages if item.topic == topic)
    link = str(letter.payload["link"])
    return link.split("token=")[1]


async def test_registration_creates_user_and_queues_letter(db_session: AsyncSession) -> None:
    await _auth(db_session).register(
        email="User@Example.ORG", password=PASSWORD, language="ru"
    )

    user = await UserRepository(db_session).get_by_email("user@example.org")
    assert user is not None
    assert user.email == "user@example.org"
    assert user.email_verified_at is None
    assert user.password_hash is not None
    assert user.referral_code

    messages = await OutboxRepository(db_session).take_batch(limit=10, now=datetime.now(UTC))
    assert [item.topic for item in messages] == [TOPIC_EMAIL_VERIFY]
    assert messages[0].payload["to"] == "user@example.org"


async def test_login_before_verification_is_refused(db_session: AsyncSession) -> None:
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")

    with pytest.raises(AuthError) as error:
        await auth.login(email="user@example.org", password=PASSWORD, user_agent=None, ip=None)

    assert error.value.code == "email_not_verified"


async def test_verification_lets_user_in(db_session: AsyncSession) -> None:
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")
    raw = await _token_from_outbox(db_session, TOPIC_EMAIL_VERIFY)

    issued = await auth.verify_email(raw, user_agent=None, ip=None)

    assert issued.access_token
    user = await UserRepository(db_session).get_by_email("user@example.org")
    assert user is not None
    assert user.email_verified_at is not None


async def test_verification_token_works_once(db_session: AsyncSession) -> None:
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")
    raw = await _token_from_outbox(db_session, TOPIC_EMAIL_VERIFY)
    await auth.verify_email(raw, user_agent=None, ip=None)

    with pytest.raises(AuthError) as error:
        await auth.verify_email(raw, user_agent=None, ip=None)

    assert error.value.code == "token_invalid"


async def test_login_with_wrong_password_and_unknown_email_look_alike(
    db_session: AsyncSession,
) -> None:
    """Ответ не должен сообщать, зарегистрирован ли адрес."""
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")
    raw = await _token_from_outbox(db_session, TOPIC_EMAIL_VERIFY)
    await auth.verify_email(raw, user_agent=None, ip=None)

    with pytest.raises(AuthError) as wrong:
        await auth.login(email="user@example.org", password="другой пароль", user_agent=None, ip=None)
    with pytest.raises(AuthError) as unknown:
        await auth.login(email="nobody@example.org", password=PASSWORD, user_agent=None, ip=None)

    assert wrong.value.code == unknown.value.code == "invalid_credentials"


async def test_second_registration_on_verified_email_is_refused(db_session: AsyncSession) -> None:
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")
    raw = await _token_from_outbox(db_session, TOPIC_EMAIL_VERIFY)
    await auth.verify_email(raw, user_agent=None, ip=None)

    with pytest.raises(AuthError) as error:
        await auth.register(email="user@example.org", password=PASSWORD, language="ru")

    assert error.value.code == "email_taken"


async def test_registration_on_unverified_email_resends_letter(db_session: AsyncSession) -> None:
    """Неподтверждённый аккаунт не должен занимать адрес навсегда.

    Опечатка в пароле при регистрации, закрытая вкладка, потерянное письмо —
    человек повторяет регистрацию, и это должно работать.
    """
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")

    await auth.register(email="user@example.org", password="другой длинный пароль", language="en")

    users = await UserRepository(db_session).get_by_email("user@example.org")
    assert users is not None
    assert users.language == "en"
    messages = await OutboxRepository(db_session).take_batch(limit=10, now=datetime.now(UTC))
    assert len(messages) == 2


async def test_weak_password_is_refused(db_session: AsyncSession) -> None:
    with pytest.raises(AuthError) as error:
        await _auth(db_session).register(email="user@example.org", password="короткий", language="ru")

    assert error.value.code == "weak_password"


async def test_reset_replaces_password_and_revokes_sessions(db_session: AsyncSession) -> None:
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")
    verify = await _token_from_outbox(db_session, TOPIC_EMAIL_VERIFY)
    old_session = await auth.verify_email(verify, user_agent=None, ip=None)

    await auth.request_reset("user@example.org")
    raw = await _token_from_outbox(db_session, "email.password_reset")
    await auth.reset(raw, "новый совершенно обычный пароль", user_agent=None, ip=None)

    await auth.login(
        email="user@example.org",
        password="новый совершенно обычный пароль",
        user_agent=None,
        ip=None,
    )
    assert old_session.refresh_token is not None
    with pytest.raises(AuthError):
        await auth._auth.refresh(old_session.refresh_token, user_agent=None, ip=None)  # noqa: SLF001


async def test_reset_for_unknown_email_is_silent(db_session: AsyncSession) -> None:
    """Ответ одинаковый, письма нет: иначе форма превращается в проверку адресов."""
    await _auth(db_session).request_reset("nobody@example.org")

    assert await OutboxRepository(db_session).take_batch(limit=10, now=datetime.now(UTC)) == []


async def test_second_reset_request_kills_the_first_link(db_session: AsyncSession) -> None:
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")
    verify = await _token_from_outbox(db_session, TOPIC_EMAIL_VERIFY)
    await auth.verify_email(verify, user_agent=None, ip=None)

    await auth.request_reset("user@example.org")
    first = await _token_from_outbox(db_session, "email.password_reset")
    await auth.request_reset("user@example.org")

    tokens = TokenRepository(db_session)
    assert (
        await tokens.find_usable(
            TokenType.password_reset, hash_opaque_token(first), datetime.now(UTC)
        )
        is None
    )


async def test_expired_verification_token_is_refused(db_session: AsyncSession) -> None:
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")
    raw = await _token_from_outbox(db_session, TOPIC_EMAIL_VERIFY)
    token = await TokenRepository(db_session).find_usable(
        TokenType.email_verify, hash_opaque_token(raw), datetime.now(UTC)
    )
    assert token is not None
    token.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    with pytest.raises(AuthError):
        await auth.verify_email(raw, user_agent=None, ip=None)
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Run: `uv run pytest backend/core/tests/test_auth_password.py -v -m docker`
Expected: FAIL — модуля `services.auth.password` нет.

- [ ] **Шаг 3: Реализовать сервис**

```python
"""Вход паролем: регистрация, подтверждение адреса, вход, сброс.

Способ входа опознаёт человека и передаёт его AuthService — токены выдаёт
только он. Здесь же живут письма: у них тот же жизненный цикл, что у пароля.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import TokenType, User
from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.db.repositories.tokens import TokenRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.domain.identity import (
    TOKEN_LIFETIMES,
    PasswordPolicyError,
    normalize_email,
    validate_password,
)
from repibot_core.security.passwords import DUMMY_HASH, hash_password, verify_password
from repibot_core.security.tokens import generate_opaque_token, hash_opaque_token
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError, IssuedSession
from repibot_core.services.email_dispatch import (
    TOPIC_EMAIL_CHANGE,
    TOPIC_EMAIL_VERIFY,
    TOPIC_PASSWORD_RESET,
)
from repibot_core.settings import Settings

logger = logging.getLogger(__name__)

_LINK_PATHS = {
    TokenType.email_verify: "/verify-email",
    TokenType.password_reset: "/reset-password",
    # Публичный путь, а не раздел кабинета: письмо открывают в том браузере,
    # где почта, и гейт кабинета увёл бы человека на вход, потеряв токен.
    TokenType.email_change: "/confirm-email",
}
_TOPICS = {
    TokenType.email_verify: TOPIC_EMAIL_VERIFY,
    TokenType.password_reset: TOPIC_PASSWORD_RESET,
    TokenType.email_change: TOPIC_EMAIL_CHANGE,
}


class PasswordAuth:
    def __init__(self, session: AsyncSession, settings: Settings, auth: AuthService) -> None:
        self._session = session
        self._settings = settings
        self._auth = auth
        self._users = UserRepository(session)
        self._tokens = TokenRepository(session)
        self._outbox = OutboxRepository(session)

    async def register(self, *, email: str, password: str, language: str) -> None:
        address = normalize_email(email)
        try:
            validate_password(password, email=address)
        except PasswordPolicyError as error:
            raise AuthError("weak_password", str(error)) from error

        existing = await self._users.get_by_email(address)
        if existing is not None and existing.email_verified_at is not None:
            raise AuthError("email_taken", "адрес уже занят")

        if existing is not None:
            # Аккаунт есть, но адрес не подтверждён: значит войти им никто не
            # может. Перезаписываем пароль и язык и отправляем письмо заново —
            # иначе брошенная регистрация занимает адрес навсегда.
            existing.password_hash = hash_password(password)
            existing.language = language
            user = existing
        else:
            user = await self._users.create(
                email=address,
                password_hash=hash_password(password),
                language=language,
                referral_code=await self._users.next_referral_code(),
            )

        await self._issue_letter(user, TokenType.email_verify)
        await self._commit_and_notify()

    async def resend_verification(self, email: str) -> None:
        """Повторное письмо. Ответ вызывающему одинаков в любом случае."""
        user = await self._users.get_by_email(email)
        if user is None or user.email_verified_at is not None:
            return
        await self._issue_letter(user, TokenType.email_verify)
        await self._commit_and_notify()

    async def verify_email(
        self, raw_token: str, *, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        token = await self._consume(TokenType.email_verify, raw_token)
        user = await self._require_user(token.user_id)

        if user.email_verified_at is None:
            user.email_verified_at = datetime.now(UTC)
        await self._session.commit()

        # Сессия выдаётся сразу: человек уже подтвердил владение адресом,
        # заставлять его вводить пароль на следующем экране незачем.
        return await self._auth.issue(user, user_agent=user_agent, ip=ip, with_refresh=True)

    async def login(
        self, *, email: str, password: str, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        user = await self._users.get_by_email(email)
        # Хеш сверяется даже для неизвестного адреса: без этого время ответа
        # сообщает, зарегистрирован ли он.
        stored = user.password_hash if user is not None else DUMMY_HASH
        matches = verify_password(stored, password)

        if user is None or not matches:
            raise AuthError("invalid_credentials", "неверный адрес или пароль")
        if user.email_verified_at is None:
            raise AuthError("email_not_verified", "адрес не подтверждён")

        return await self._auth.issue(user, user_agent=user_agent, ip=ip, with_refresh=True)

    async def request_reset(self, email: str) -> None:
        user = await self._users.get_by_email(email)
        if user is None or user.email is None:
            logger.info("сброс пароля запрошен для неизвестного адреса")
            return
        await self._issue_letter(user, TokenType.password_reset)
        await self._commit_and_notify()

    async def reset(
        self, raw_token: str, new_password: str, *, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        token = await self._consume(TokenType.password_reset, raw_token)
        user = await self._require_user(token.user_id)

        try:
            validate_password(new_password, email=user.email)
        except PasswordPolicyError as error:
            raise AuthError("weak_password", str(error)) from error

        user.password_hash = hash_password(new_password)
        # Сброс пароля — это либо забытый пароль, либо угон. В обоих случаях
        # прежние сессии должны прекратиться.
        await self._session.commit()
        await self._auth.revoke_all_sessions(user.id)

        return await self._auth.issue(user, user_agent=user_agent, ip=ip, with_refresh=True)

    async def _issue_letter(
        self, user: User, kind: TokenType, *, payload: dict[str, Any] | None = None
    ) -> None:
        """Создаёт одноразовый токен и ставит письмо в очередь.

        Прежние токены того же типа гасятся: две рабочие ссылки на сброс
        пароля — это две возможности им воспользоваться.
        """
        await self._tokens.invalidate_all(kind, user.id)

        raw = generate_opaque_token()
        await self._tokens.create(
            type=kind,
            user_id=user.id,
            token_hash=hash_opaque_token(raw),
            expires_at=datetime.now(UTC) + TOKEN_LIFETIMES[kind],
            payload=payload,
        )

        recipient = payload.get("email") if payload else user.email
        if recipient is None:
            msg = "письмо некуда отправить"
            raise AuthError("token_invalid", msg)

        await self._outbox.add(
            _TOPICS[kind],
            {
                "to": recipient,
                "language": user.language,
                "link": f"{self._settings.public_web_url}{_LINK_PATHS[kind]}?token={raw}",
            },
        )

    async def _consume(self, kind: TokenType, raw_token: str) -> Any:
        token = await self._tokens.find_usable(
            kind, hash_opaque_token(raw_token), datetime.now(UTC)
        )
        if token is None:
            raise AuthError("token_invalid", "ссылка недействительна или уже использована")
        await self._tokens.mark_used(token)
        return token

    async def _require_user(self, user_id: int) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthError("token_invalid", "пользователь не найден")
        return user

    async def _commit_and_notify(self) -> None:
        """Фиксирует транзакцию и просит воркер разобрать очередь сейчас.

        Постановка задачи идёт после коммита: до него письма в базе ещё нет,
        и воркер, успевший начать работу, ничего бы не нашёл. Отказ брокера не
        отменяет регистрацию — очередь всё равно разберётся по расписанию.
        """
        await self._session.commit()

        from repibot_core.tasks import process_outbox

        try:
            await process_outbox.kiq()
        except Exception:  # noqa: BLE001 — недоступный брокер не должен ломать регистрацию
            logger.warning("не удалось поставить задачу разбора outbox", exc_info=True)
```

- [ ] **Шаг 4: Убедиться, что тесты проходят**

Run: `uv run pytest backend/core/tests/test_auth_password.py -v -m docker`
Expected: PASS (12 тестов).

В тестах брокер недоступен — задача не поставится, и в журнале будет предупреждение. Это ожидаемое поведение: письма всё равно достаются из `outbox` напрямую.

- [ ] **Шаг 5: Коммит**

```bash
git add backend/core/src/repibot_core/services/auth/password.py backend/core/tests/test_auth_password.py
git commit -m "feat: регистрация, подтверждение почты и вход паролем"
```

---

## Задача 11: Профиль, смена почты и пароля

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/profile.py`
- Тест: `backend/core/tests/test_profile.py`

**Интерфейсы:**
- Отдаёт: `ProfileView` (dataclass: `user_id: int`, `email: str | None`, `email_verified: bool`, `telegram_username: str | None`, `name: str | None`, `language: str`, `role: UserRole`, `referral_code: str`, `has_password: bool`, `has_telegram: bool`, `passkey_count: int`); `SessionView` (dataclass: `session_id: UUID`, `user_agent: str | None`, `ip: str | None`, `created_at: datetime`, `is_current: bool`); `ProfileService(session, settings, auth, principals, letters: PasswordAuth)` с методами `view(user_id) -> ProfileView`, `update(user_id, *, name, language) -> ProfileView`, `set_password(user_id, *, current, new) -> None`, `request_email_change(user_id, new_email) -> None`, `confirm_email_change(raw_token) -> None`, `list_sessions(user_id, current_id) -> list[SessionView]`.
- Коды ошибок: `invalid_credentials` (неверный текущий пароль), `weak_password`, `email_taken`, `token_invalid`, `not_found`.

- [ ] **Шаг 1: Написать падающий тест**

```python
"""Профиль: язык, имя, пароль, адрес почты, список сессий."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.security.passwords import verify_password
from repibot_core.services.auth.password import PasswordAuth
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError
from repibot_core.services.principal import PrincipalCache
from repibot_core.services.profile import ProfileService
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker

PASSWORD = "совершенно обычный пароль"


def _services(session: AsyncSession) -> tuple[PasswordAuth, ProfileService]:
    settings = get_settings()
    principals = PrincipalCache(FakeRedis())
    auth = AuthService(session, settings, principals)
    letters = PasswordAuth(session, settings, auth)
    return letters, ProfileService(session, settings, auth, principals, letters)


async def _verified_user(session: AsyncSession) -> int:
    letters, _ = _services(session)
    await letters.register(email="user@example.org", password=PASSWORD, language="ru")
    messages = await OutboxRepository(session).take_batch(limit=10, now=datetime.now(UTC))
    raw = str(messages[0].payload["link"]).split("token=")[1]
    await letters.verify_email(raw, user_agent=None, ip=None)
    user = await UserRepository(session).get_by_email("user@example.org")
    assert user is not None
    return user.id


async def test_view_reports_login_methods(db_session: AsyncSession) -> None:
    user_id = await _verified_user(db_session)
    _, profile = _services(db_session)

    view = await profile.view(user_id)

    assert view.email == "user@example.org"
    assert view.email_verified is True
    assert view.has_password is True
    assert view.has_telegram is False
    assert view.passkey_count == 0
    assert view.referral_code


async def test_language_change_is_saved(db_session: AsyncSession) -> None:
    user_id = await _verified_user(db_session)
    _, profile = _services(db_session)

    updated = await profile.update(user_id, name="Имя", language="en")

    assert updated.language == "en"
    assert updated.name == "Имя"


async def test_password_change_requires_current_one(db_session: AsyncSession) -> None:
    user_id = await _verified_user(db_session)
    _, profile = _services(db_session)

    with pytest.raises(AuthError) as error:
        await profile.set_password(user_id, current="неверный", new="другой длинный пароль")

    assert error.value.code == "invalid_credentials"


async def test_password_change_stores_new_hash(db_session: AsyncSession) -> None:
    user_id = await _verified_user(db_session)
    _, profile = _services(db_session)

    await profile.set_password(user_id, current=PASSWORD, new="другой длинный пароль")

    user = await UserRepository(db_session).get(user_id)
    assert user is not None
    assert verify_password(user.password_hash, "другой длинный пароль") is True


async def test_email_change_needs_confirmation(db_session: AsyncSession) -> None:
    """Адрес меняется только после подтверждения нового.

    Иначе опечатка в адресе отбирает доступ: почта — способ входа.
    """
    user_id = await _verified_user(db_session)
    _, profile = _services(db_session)

    await profile.request_email_change(user_id, "new@example.org")

    user = await UserRepository(db_session).get(user_id)
    assert user is not None
    assert user.email == "user@example.org"

    messages = await OutboxRepository(db_session).take_batch(limit=10, now=datetime.now(UTC))
    letter = next(item for item in messages if item.topic == "email.change")
    assert letter.payload["to"] == "new@example.org"

    raw = str(letter.payload["link"]).split("token=")[1]
    await profile.confirm_email_change(raw)

    user = await UserRepository(db_session).get(user_id)
    assert user is not None
    assert user.email == "new@example.org"


async def test_email_change_to_taken_address_is_refused(db_session: AsyncSession) -> None:
    first = await _verified_user(db_session)
    letters, profile = _services(db_session)
    await letters.register(email="second@example.org", password=PASSWORD, language="ru")

    with pytest.raises(AuthError) as error:
        await profile.request_email_change(first, "second@example.org")

    assert error.value.code == "email_taken"


async def test_sessions_list_marks_current(db_session: AsyncSession) -> None:
    user_id = await _verified_user(db_session)
    settings = get_settings()
    principals = PrincipalCache(FakeRedis())
    auth = AuthService(db_session, settings, principals)
    user = await UserRepository(db_session).get(user_id)
    assert user is not None
    current = await auth.issue(user, user_agent="pytest", ip="127.0.0.1", with_refresh=True)
    await auth.issue(user, user_agent="other", ip="10.0.0.1", with_refresh=True)
    _, profile = _services(db_session)

    items = await profile.list_sessions(user_id, current.session_id)

    assert len(items) == 3  # подтверждение почты выдало ещё одну
    assert [item.is_current for item in items].count(True) == 1
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Run: `uv run pytest backend/core/tests/test_profile.py -v -m docker`
Expected: FAIL — модуля `services.profile` нет.

- [ ] **Шаг 3: Реализовать сервис**

```python
"""Профиль: то, что пользователь меняет о себе сам."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import TokenType, UserRole
from repibot_core.db.repositories.sessions import SessionRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.domain.identity import PasswordPolicyError, normalize_email, validate_password
from repibot_core.security.passwords import hash_password, verify_password
from repibot_core.services.auth.password import PasswordAuth
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError
from repibot_core.services.principal import PrincipalCache
from repibot_core.settings import Settings


@dataclass(frozen=True, slots=True)
class ProfileView:
    user_id: int
    email: str | None
    email_verified: bool
    telegram_username: str | None
    name: str | None
    language: str
    role: UserRole
    referral_code: str
    has_password: bool
    has_telegram: bool
    passkey_count: int


@dataclass(frozen=True, slots=True)
class SessionView:
    session_id: UUID
    user_agent: str | None
    ip: str | None
    created_at: datetime
    is_current: bool


class ProfileService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        auth: AuthService,
        principals: PrincipalCache,
        letters: PasswordAuth,
    ) -> None:
        self._session = session
        self._settings = settings
        self._auth = auth
        self._principals = principals
        self._letters = letters
        self._users = UserRepository(session)
        self._sessions = SessionRepository(session)

    async def view(self, user_id: int) -> ProfileView:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthError("not_found", "пользователь не найден")
        return ProfileView(
            user_id=user.id,
            email=user.email,
            email_verified=user.email_verified_at is not None,
            telegram_username=user.telegram_username,
            name=user.name,
            language=user.language,
            role=user.role,
            referral_code=user.referral_code,
            has_password=user.password_hash is not None,
            has_telegram=user.telegram_id is not None,
            # Passkey появятся в плане 1b; до тех пор их ноль, и это честное
            # значение, а не заглушка: таблицы ещё нет.
            passkey_count=0,
        )

    async def update(self, user_id: int, *, name: str | None, language: str) -> ProfileView:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthError("not_found", "пользователь не найден")
        if language not in self._settings.supported_languages:
            raise AuthError("validation_error", "язык не поддерживается")

        user.name = name
        user.language = language
        await self._session.commit()
        # Язык лежит в кэше вместе с ролью: без сброса бот ответит на прежнем.
        await self._principals.invalidate(user_id)
        return await self.view(user_id)

    async def set_password(self, user_id: int, *, current: str | None, new: str) -> None:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthError("not_found", "пользователь не найден")

        # Пароля может не быть вовсе — у вошедшего через Telegram. Тогда это
        # установка первого пароля, и текущий спрашивать не с чего.
        if user.password_hash is not None and not verify_password(user.password_hash, current or ""):
            raise AuthError("invalid_credentials", "текущий пароль неверен")

        try:
            validate_password(new, email=user.email)
        except PasswordPolicyError as error:
            raise AuthError("weak_password", str(error)) from error

        user.password_hash = hash_password(new)
        await self._session.commit()

    async def request_email_change(self, user_id: int, new_email: str) -> None:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthError("not_found", "пользователь не найден")

        address = normalize_email(new_email)
        occupied = await self._users.get_by_email(address)
        if occupied is not None and occupied.id != user_id:
            raise AuthError("email_taken", "адрес уже занят")

        # Письмо уходит на новый адрес, а сам адрес пока не меняется: пока
        # владение им не доказано, менять способ входа нельзя.
        await self._letters.issue_email_change(user, address)

    async def confirm_email_change(self, raw_token: str) -> None:
        await self._letters.apply_email_change(raw_token)

    async def list_sessions(self, user_id: int, current_id: UUID) -> list[SessionView]:
        return [
            SessionView(
                session_id=item.id,
                user_agent=item.user_agent,
                ip=item.ip,
                created_at=item.created_at,
                is_current=item.id == current_id,
            )
            for item in await self._sessions.list_active(user_id)
        ]
```

- [ ] **Шаг 4: Дополнить `PasswordAuth` двумя методами**

Смена адреса пользуется тем же механизмом токенов и писем, что и подтверждение, поэтому живёт рядом с ним, а не дублируется в профиле. Добавить в `services/auth/password.py`:

```python
    async def issue_email_change(self, user: User, new_email: str) -> None:
        """Письмо на новый адрес. Сам адрес меняется только после подтверждения."""
        await self._issue_letter(
            user, TokenType.email_change, payload={"email": new_email}
        )
        await self._commit_and_notify()

    async def apply_email_change(self, raw_token: str) -> None:
        """Подтверждение приходит письмом и может открыться в другом браузере.

        Поэтому операция авторизуется самим токеном, а не сессией: требовать
        вход в том же браузере значило бы ломать нормальный сценарий.
        """
        token = await self._consume(TokenType.email_change, raw_token)
        user = await self._require_user(token.user_id)

        address = str((token.payload or {}).get("email", ""))
        if not address:
            raise AuthError("token_invalid", "в токене нет адреса")

        occupied = await self._users.get_by_email(address)
        if occupied is not None and occupied.id != user.id:
            raise AuthError("email_taken", "адрес уже занят")

        user.email = address
        user.email_verified_at = datetime.now(UTC)
        await self._session.commit()
```

- [ ] **Шаг 5: Убедиться, что тесты проходят**

Run: `uv run pytest backend/core/tests/test_profile.py -v -m docker`
Expected: PASS (7 тестов).

- [ ] **Шаг 6: Коммит**

```bash
git add backend/core/src/repibot_core/services/profile.py backend/core/src/repibot_core/services/auth/password.py backend/core/tests/test_profile.py
git commit -m "feat: профиль, смена пароля и адреса почты"
```

---

## Задача 12: Вход из MiniApp

**Файлы:**
- Создать: `backend/core/src/repibot_core/security/initdata.py`, `backend/core/src/repibot_core/services/auth/telegram.py`
- Создать: `backend/core/src/repibot_core/testing/__init__.py`, `backend/core/src/repibot_core/testing/initdata.py`
- Тест: `backend/core/tests/test_initdata.py`, `backend/core/tests/test_auth_telegram.py`

**Интерфейсы:**
- Отдаёт: `TelegramUser` (dataclass: `telegram_id: int`, `username: str | None`, `first_name: str | None`, `language_code: str | None`); `InitDataError`; `parse_init_data(raw: str, *, bot_token: str, max_age: timedelta, now: datetime | None = None) -> TelegramUser`; `TelegramAuth(session, settings, auth)` с методом `login_from_miniapp(raw_init_data, *, ip) -> IssuedSession`.

- [ ] **Шаг 1: Написать падающий тест проверки подписи**

```python
"""Проверка initData. Подпись считается ровно так, как её ставит Telegram."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest

from repibot_core.security.initdata import InitDataError, parse_init_data

BOT_TOKEN = "123456:test-token"


def _sign(fields: dict[str, str], token: str = BOT_TOKEN) -> str:
    """Собирает initData так же, как Telegram: сортировка, перевод строки, HMAC."""
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


def _fields(auth_date: datetime | None = None) -> dict[str, str]:
    moment = auth_date or datetime.now(UTC)
    user = (
        '{"id":777,"first_name":"Иван","username":"ivan","language_code":"ru"}'
    )
    return {"auth_date": str(int(moment.timestamp())), "user": user, "query_id": "AAA"}


def test_valid_init_data_is_parsed() -> None:
    parsed = parse_init_data(_sign(_fields()), bot_token=BOT_TOKEN, max_age=timedelta(days=1))

    assert parsed.telegram_id == 777
    assert parsed.username == "ivan"
    assert parsed.language_code == "ru"


def test_tampered_init_data_is_rejected() -> None:
    raw = _sign(_fields()).replace("777", "888")

    with pytest.raises(InitDataError):
        parse_init_data(raw, bot_token=BOT_TOKEN, max_age=timedelta(days=1))


def test_data_signed_with_another_token_is_rejected() -> None:
    raw = _sign(_fields(), token="999999:другой-токен")

    with pytest.raises(InitDataError):
        parse_init_data(raw, bot_token=BOT_TOKEN, max_age=timedelta(days=1))


def test_old_init_data_is_rejected() -> None:
    """Сутки — предел. Просроченный initData означает переигранный запрос."""
    raw = _sign(_fields(datetime.now(UTC) - timedelta(days=2)))

    with pytest.raises(InitDataError):
        parse_init_data(raw, bot_token=BOT_TOKEN, max_age=timedelta(days=1))


def test_init_data_without_hash_is_rejected() -> None:
    with pytest.raises(InitDataError):
        parse_init_data("auth_date=1&user=%7B%7D", bot_token=BOT_TOKEN, max_age=timedelta(days=1))


def test_empty_init_data_is_rejected() -> None:
    with pytest.raises(InitDataError):
        parse_init_data("", bot_token=BOT_TOKEN, max_age=timedelta(days=1))
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_initdata.py -v`
Expected: FAIL — модуля нет.

- [ ] **Шаг 3: Реализовать проверку**

```python
"""Проверка initData из Telegram MiniApp.

Схема задана Telegram: строка проверки — отсортированные пары ключ=значение
через перевод строки, ключ — HMAC от токена бота на строке "WebAppData".
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl


class InitDataError(Exception):
    """initData отсутствует, подделан или устарел."""


@dataclass(frozen=True, slots=True)
class TelegramUser:
    telegram_id: int
    username: str | None
    first_name: str | None
    language_code: str | None


def parse_init_data(
    raw: str, *, bot_token: str, max_age: timedelta, now: datetime | None = None
) -> TelegramUser:
    if not raw:
        raise InitDataError("initData пуст")

    fields = dict(parse_qsl(raw, strict_parsing=False))
    signature = fields.pop("hash", None)
    if signature is None:
        raise InitDataError("в initData нет подписи")

    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()

    # compare_digest, а не ==: сравнение строк выходит из цикла на первом
    # различии, и по времени ответа подпись подбирается побайтово.
    # Сравниваются байты, а не строки: строковый вариант compare_digest падает
    # с TypeError на не-ASCII подписи, а её присылает кто угодно.
    if not hmac.compare_digest(expected.encode(), signature.encode()):
        raise InitDataError("подпись initData не совпала")

    try:
        auth_date = datetime.fromtimestamp(int(fields["auth_date"]), tz=UTC)
    except (KeyError, ValueError) as error:
        raise InitDataError("некорректный auth_date") from error

    if (now or datetime.now(UTC)) - auth_date > max_age:
        raise InitDataError("initData устарел")

    try:
        user = json.loads(fields["user"])
        return TelegramUser(
            telegram_id=int(user["id"]),
            username=user.get("username"),
            first_name=user.get("first_name"),
            language_code=user.get("language_code"),
        )
    except (KeyError, ValueError, TypeError) as error:
        raise InitDataError("в initData нет пользователя") from error
```

- [ ] **Шаг 4: Сборщик initData для тестов**

Тест самой проверки подписывает данные вручную — это правильно, независимая реализация ловит ошибку в основной. Всем остальным (тесты входа, тесты API, сквозные сценарии) нужен готовый валидный `initData`, и собирать его в трёх местах незачем.

Создать `backend/core/src/repibot_core/testing/initdata.py`:

```python
"""Сборка initData для тестов и локальной отладки.

Лежит в пакете, а не в тестах: тем же способом MiniApp проверяется руками, и
дублировать подпись в каждом наборе тестов не нужно.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from urllib.parse import urlencode


def build_init_data(
    *,
    bot_token: str,
    telegram_id: int = 777,
    username: str | None = "ivan",
    first_name: str = "Иван",
    language_code: str = "ru",
    auth_date: datetime | None = None,
) -> str:
    user = json.dumps(
        {
            "id": telegram_id,
            "first_name": first_name,
            "username": username,
            "language_code": language_code,
        },
        ensure_ascii=False,
    )
    fields = {
        "auth_date": str(int((auth_date or datetime.now(UTC)).timestamp())),
        "user": user,
        "query_id": "AAA",
    }
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})
```

- [ ] **Шаг 5: Написать падающий тест входа**

```python
"""Вход из MiniApp: создание аккаунта по telegram_id и повторный вход."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.users import UserRepository
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.telegram import TelegramAuth
from repibot_core.services.auth.types import AuthError
from repibot_core.services.principal import PrincipalCache
from repibot_core.settings import get_settings
from repibot_core.testing.initdata import build_init_data

pytestmark = pytest.mark.docker

BOT_TOKEN = "123456:test-token"


def _telegram(session: AsyncSession) -> TelegramAuth:
    settings = get_settings()
    return TelegramAuth(
        session, settings, AuthService(session, settings, PrincipalCache(FakeRedis()))
    )


async def test_first_open_creates_account(db_session: AsyncSession) -> None:
    issued = await _telegram(db_session).login_from_miniapp(
        build_init_data(bot_token=BOT_TOKEN), ip="127.0.0.1"
    )

    assert issued.access_token
    # В MiniApp cookie не выживает — refresh не выдаётся.
    assert issued.refresh_token is None

    user = await UserRepository(db_session).get_by_telegram_id(777)
    assert user is not None
    assert user.language == "ru"
    assert user.email is None
    assert user.referral_code


async def test_second_open_reuses_account(db_session: AsyncSession) -> None:
    telegram = _telegram(db_session)
    first = await telegram.login_from_miniapp(build_init_data(bot_token=BOT_TOKEN), ip=None)

    second = await telegram.login_from_miniapp(build_init_data(bot_token=BOT_TOKEN), ip=None)

    assert first.session_id != second.session_id
    users = UserRepository(db_session)
    assert await users.get_by_telegram_id(777) is not None


async def test_username_is_refreshed_on_login(db_session: AsyncSession) -> None:
    """Имя пользователя меняется на стороне Telegram, и мы обязаны догонять."""
    telegram = _telegram(db_session)
    await telegram.login_from_miniapp(build_init_data(bot_token=BOT_TOKEN), ip=None)

    await telegram.login_from_miniapp(
        build_init_data(bot_token=BOT_TOKEN, username="ivan_new"), ip=None
    )

    user = await UserRepository(db_session).get_by_telegram_id(777)
    assert user is not None
    assert user.telegram_username == "ivan_new"


async def test_tampered_init_data_is_refused(db_session: AsyncSession) -> None:
    with pytest.raises(AuthError) as error:
        await _telegram(db_session).login_from_miniapp("hash=подделка", ip=None)

    assert error.value.code == "invalid_credentials"


async def test_admin_from_env_gets_role(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "777")
    get_settings.cache_clear()

    await _telegram(db_session).login_from_miniapp(build_init_data(bot_token=BOT_TOKEN), ip=None)

    user = await UserRepository(db_session).get_by_telegram_id(777)
    assert user is not None
    assert user.role.value == "admin"

    get_settings.cache_clear()
```

- [ ] **Шаг 6: Реализовать вход**

```python
"""Вход через Telegram: MiniApp.

Вход в браузере через OIDC добавляется планом 1b и встанет рядом — тем же
способом: опознать, отдать пользователя AuthService.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.db.repositories.users import UserRepository
from repibot_core.security.initdata import InitDataError, TelegramUser, parse_init_data
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError, IssuedSession
from repibot_core.settings import Settings

logger = logging.getLogger(__name__)

# Сутки — предел свежести initData. Telegram выдаёт его при каждом открытии,
# и суточной давности значение означает переигранный запрос.
INIT_DATA_MAX_AGE = timedelta(days=1)


class TelegramAuth:
    def __init__(self, session: AsyncSession, settings: Settings, auth: AuthService) -> None:
        self._session = session
        self._settings = settings
        self._auth = auth
        self._users = UserRepository(session)

    async def login_from_miniapp(self, raw_init_data: str, *, ip: str | None) -> IssuedSession:
        try:
            parsed = parse_init_data(
                raw_init_data,
                bot_token=self._settings.bot_token.get_secret_value(),
                max_age=INIT_DATA_MAX_AGE,
            )
        except InitDataError as error:
            # Наружу уходит общий код: подробность «подпись не совпала» или
            # «устарел» помогает только тому, кто подбирает подпись.
            logger.warning("отклонён initData: %s", error)
            raise AuthError("invalid_credentials", "initData не принят") from error

        user = await self._find_or_create(parsed)
        # Refresh не выдаётся: в веб-версии Telegram наш домен оказывается в
        # стороннем контексте, и cookie там не переживёт перезагрузку.
        return await self._auth.issue(
            user, user_agent="telegram-miniapp", ip=ip, with_refresh=False
        )

    async def _find_or_create(self, parsed: TelegramUser) -> User:
        user = await self._users.get_by_telegram_id(parsed.telegram_id)
        if user is not None:
            user.telegram_username = parsed.username
            if user.name is None:
                user.name = parsed.first_name
            await self._session.flush()
            return user

        language = self._pick_language(parsed.language_code)
        return await self._users.create(
            telegram_id=parsed.telegram_id,
            telegram_username=parsed.username,
            name=parsed.first_name,
            language=language,
            referral_code=await self._users.next_referral_code(),
        )

    def _pick_language(self, code: str | None) -> str:
        """Язык из Telegram — только начальное значение.

        Дальше он меняется исключительно пользователем: перенастройка Telegram
        не должна переключать язык кабинета.
        """
        if code is None:
            return self._settings.default_language
        short = code.split("-")[0]
        return short if short in self._settings.supported_languages else self._settings.default_language
```

- [ ] **Шаг 7: Убедиться, что тесты проходят**

Run: `uv run pytest backend/core/tests/test_initdata.py backend/core/tests/test_auth_telegram.py -v -m docker`
Expected: PASS (6 + 5 тестов).

- [ ] **Шаг 8: Коммит**

```bash
git add backend/core/src/repibot_core/security/initdata.py backend/core/src/repibot_core/services/auth/telegram.py backend/core/src/repibot_core/testing backend/core/tests/test_initdata.py backend/core/tests/test_auth_telegram.py
git commit -m "feat: вход из MiniApp по initData"
```

---

## Задача 13: Ограничение частоты запросов

**Файлы:**
- Создать: `backend/core/src/repibot_core/ratelimit.py`
- Тест: `backend/core/tests/test_ratelimit.py`

**Интерфейсы:**
- Отдаёт: `Rule` (dataclass: `limit: int`, `window: timedelta`); `RateLimitResult` (dataclass: `allowed: bool`, `retry_after_seconds: int`); `RateLimiter(redis)` с методом `hit(key: str, rule: Rule, *, now: datetime | None = None) -> RateLimitResult`; правила `LOGIN_PER_IP`, `LOGIN_PER_EMAIL`, `REGISTER_PER_IP`, `LETTER_PER_EMAIL`, `LETTER_PER_IP`, `MINIAPP_PER_IP`.

- [ ] **Шаг 1: Написать падающий тест**

```python
"""Скользящее окно на Valkey."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fakeredis.aioredis import FakeRedis

from repibot_core.ratelimit import (
    LOGIN_PER_EMAIL,
    LOGIN_PER_IP,
    RateLimiter,
    Rule,
)

RULE = Rule(limit=3, window=timedelta(minutes=1))


async def test_requests_under_limit_are_allowed() -> None:
    limiter = RateLimiter(FakeRedis())

    for _ in range(3):
        assert (await limiter.hit("k", RULE)).allowed is True


async def test_request_over_limit_is_refused_with_retry_after() -> None:
    limiter = RateLimiter(FakeRedis())
    for _ in range(3):
        await limiter.hit("k", RULE)

    result = await limiter.hit("k", RULE)

    assert result.allowed is False
    assert 0 < result.retry_after_seconds <= 60


async def test_window_slides() -> None:
    """Окно скользящее: через минуту после первых попыток счёт обнуляется."""
    limiter = RateLimiter(FakeRedis())
    start = datetime.now(UTC)
    for _ in range(3):
        await limiter.hit("k", RULE, now=start)

    later = await limiter.hit("k", RULE, now=start + timedelta(seconds=61))

    assert later.allowed is True


async def test_keys_are_independent() -> None:
    limiter = RateLimiter(FakeRedis())
    for _ in range(3):
        await limiter.hit("first", RULE)

    assert (await limiter.hit("second", RULE)).allowed is True


def test_rules_match_the_spec() -> None:
    assert LOGIN_PER_IP == Rule(limit=10, window=timedelta(minutes=1))
    assert LOGIN_PER_EMAIL == Rule(limit=5, window=timedelta(minutes=1))
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_ratelimit.py -v`
Expected: FAIL — модуля нет.

- [ ] **Шаг 3: Реализовать ограничитель**

```python
"""Ограничение частоты запросов.

Скользящее окно на sorted set: каждая попытка — элемент с отметкой времени,
старые вычищаются перед подсчётом. Фиксированное окно дало бы двойной лимит на
стыке периодов, а именно стык и выбирают для перебора.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class Rule:
    limit: int
    window: timedelta


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int


LOGIN_PER_IP = Rule(limit=10, window=timedelta(minutes=1))
LOGIN_PER_EMAIL = Rule(limit=5, window=timedelta(minutes=1))
REGISTER_PER_IP = Rule(limit=5, window=timedelta(hours=1))
LETTER_PER_EMAIL = Rule(limit=3, window=timedelta(hours=1))
LETTER_PER_IP = Rule(limit=10, window=timedelta(hours=1))
MINIAPP_PER_IP = Rule(limit=30, window=timedelta(minutes=1))


class RateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, key: str, rule: Rule, *, now: datetime | None = None) -> RateLimitResult:
        moment = now or datetime.now(UTC)
        timestamp = moment.timestamp()
        cutoff = timestamp - rule.window.total_seconds()
        full_key = f"ratelimit:{key}"

        pipeline = self._redis.pipeline()
        pipeline.zremrangebyscore(full_key, 0, cutoff)
        # Член множества уникален: две попытки в одну миллисекунду должны
        # считаться двумя.
        pipeline.zadd(full_key, {f"{timestamp}:{uuid4()}": timestamp})
        pipeline.zcard(full_key)
        pipeline.expire(full_key, int(rule.window.total_seconds()) + 1)
        results = await pipeline.execute()

        count = int(results[2])
        if count <= rule.limit:
            return RateLimitResult(allowed=True, retry_after_seconds=0)

        oldest = await self._redis.zrange(full_key, 0, 0, withscores=True)
        retry_after = rule.window.total_seconds()
        if oldest:
            retry_after = oldest[0][1] + rule.window.total_seconds() - timestamp
        return RateLimitResult(allowed=False, retry_after_seconds=max(1, math.ceil(retry_after)))
```

- [ ] **Шаг 4: Убедиться, что тесты проходят**

Run: `uv run pytest backend/core/tests/test_ratelimit.py -v`
Expected: PASS (5 тестов).

- [ ] **Шаг 5: Коммит**

```bash
git add backend/core/src/repibot_core/ratelimit.py backend/core/tests/test_ratelimit.py
git commit -m "feat: ограничение частоты запросов на Valkey"
```

---

## Задача 14: Зависимости API и эндпоинты входа

**Файлы:**
- Создать: `backend/api/src/repibot_api/deps.py`, `cookies.py`, `schemas.py`, `origins.py`, `routers/__init__.py`, `routers/auth.py`
- Изменить: `backend/api/src/repibot_api/main.py`, `errors.py`, `health.py`, `backend/api/tests/test_cors.py`
- Изменить: `conftest.py` (фикстура клиента API)
- Тест: `backend/api/tests/test_auth_routes.py`

**Интерфейсы:**
- Отдаёт: `get_engine()`, `get_session_factory()`, `get_redis()`, `db_session()` (зависимость), `get_principals()`, `AuthContext` (dataclass: `principal: Principal`, `session_id: UUID`), `current_context` (зависимость), `require_role(*roles)`, `client_ip(request) -> str | None`; `set_refresh_cookie(response, token, *, expires_at, secure)`, `clear_refresh_cookie(response, *, secure)`, `REFRESH_COOKIE`, `COOKIE_PATH`; функция `api_error_from(error: AuthError) -> ApiError`.
- Роутер `auth_router` с путями `/api/auth/register`, `/verify-email`, `/resend-verification`, `/login`, `/refresh`, `/logout`, `/password/forgot`, `/password/reset`, `/email/change-confirm`, `/telegram/miniapp`.

- [ ] **Шаг 1: Написать падающий тест**

Сначала фикстура. В `conftest.py`:

```python
@pytest_asyncio.fixture
async def api_client(postgres_url: str, engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """Клиент API с реальной базой и подставным Valkey.

    Postgres нужен настоящий — проверяются ограничения схемы. Valkey заменяется
    fakeredis: кэш и лимиты не зависят от особенностей сервера, а контейнер
    ради них удваивал бы время прогона.
    """
    from alembic import command
    from alembic.config import Config
    from fakeredis.aioredis import FakeRedis

    from repibot_api import deps
    from repibot_api.main import app
    from repibot_core.db.engine import create_session_factory

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", postgres_url.replace("+asyncpg", "+psycopg"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    factory = create_session_factory(engine)
    redis = FakeRedis()

    async def _session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[deps.db_session] = _session
    app.dependency_overrides[deps.get_redis] = lambda: redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://testserver") as client:
        yield client

    app.dependency_overrides.clear()
```

Импорты в conftest: `from httpx import ASGITransport, AsyncClient`.

Тест `backend/api/tests/test_auth_routes.py`:

```python
"""Эндпоинты входа: формат ответов, cookie, лимиты, проверка Origin."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from repibot_core.testing.initdata import build_init_data

pytestmark = pytest.mark.docker

PASSWORD = "совершенно обычный пароль"
ORIGIN = "https://example.org"


async def _register_and_verify(client: AsyncClient, email: str = "user@example.org") -> None:
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": PASSWORD, "language": "ru"}
    )
    assert response.status_code == 202

    from repibot_api.deps import get_session_factory

    async with get_session_factory()() as session:
        row = await session.execute(
            text("select payload from outbox where topic = 'email.verify' order by id desc limit 1")
        )
        link = str(row.scalar_one()["link"])

    token = link.split("token=")[1]
    confirmed = await client.post("/api/auth/verify-email", json={"token": token})
    assert confirmed.status_code == 200


async def test_registration_answers_202_without_leaking_anything(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/auth/register",
        json={"email": "user@example.org", "password": PASSWORD, "language": "ru"},
    )

    assert response.status_code == 202
    assert response.json() == {"status": "verification_sent"}


async def test_weak_password_returns_code(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/auth/register",
        json={"email": "user@example.org", "password": "короткий", "language": "ru"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "weak_password"


async def test_login_sets_httponly_cookie_scoped_to_refresh(api_client: AsyncClient) -> None:
    await _register_and_verify(api_client)

    response = await api_client.post(
        "/api/auth/login", json={"email": "user@example.org", "password": PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["expires_in"] == 900

    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    # Путь ограничен единственным эндпоинтом, который эту cookie читает.
    assert "Path=/api/auth/refresh" in cookie
    # Токен не должен появиться в теле ответа: там его достала бы любая XSS.
    assert "refresh" not in body


async def test_login_before_verification_returns_403(api_client: AsyncClient) -> None:
    await api_client.post(
        "/api/auth/register",
        json={"email": "user@example.org", "password": PASSWORD, "language": "ru"},
    )

    response = await api_client.post(
        "/api/auth/login", json={"email": "user@example.org", "password": PASSWORD}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "email_not_verified"


async def test_refresh_requires_matching_origin(api_client: AsyncClient) -> None:
    """Единственный эндпоинт, читающий cookie, обязан проверять Origin."""
    await _register_and_verify(api_client)
    await api_client.post(
        "/api/auth/login", json={"email": "user@example.org", "password": PASSWORD}
    )

    foreign = await api_client.post("/api/auth/refresh", headers={"Origin": "https://evil.example"})

    assert foreign.status_code == 403
    assert foreign.json()["error"]["code"] == "forbidden"


async def test_refresh_rotates_cookie(api_client: AsyncClient) -> None:
    await _register_and_verify(api_client)
    login = await api_client.post(
        "/api/auth/login", json={"email": "user@example.org", "password": PASSWORD}
    )
    first_cookie = login.headers["set-cookie"]

    refreshed = await api_client.post("/api/auth/refresh", headers={"Origin": ORIGIN})

    assert refreshed.status_code == 200
    assert refreshed.headers["set-cookie"] != first_cookie
    assert refreshed.json()["access_token"]


async def test_refresh_without_cookie_returns_401(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/auth/refresh", headers={"Origin": ORIGIN})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_logout_clears_cookie(api_client: AsyncClient) -> None:
    await _register_and_verify(api_client)
    login = await api_client.post(
        "/api/auth/login", json={"email": "user@example.org", "password": PASSWORD}
    )
    token = login.json()["access_token"]

    response = await api_client.post(
        "/api/auth/logout", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]


async def test_login_rate_limit_returns_429_with_retry_after(api_client: AsyncClient) -> None:
    await _register_and_verify(api_client)

    for _ in range(5):
        await api_client.post(
            "/api/auth/login", json={"email": "user@example.org", "password": "неверный"}
        )
    response = await api_client.post(
        "/api/auth/login", json={"email": "user@example.org", "password": "неверный"}
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert int(response.headers["retry-after"]) > 0


async def test_forgot_password_answers_the_same_for_unknown_email(api_client: AsyncClient) -> None:
    known = await api_client.post("/api/auth/password/forgot", json={"email": "user@example.org"})
    unknown = await api_client.post("/api/auth/password/forgot", json={"email": "no@example.org"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


async def test_miniapp_login_returns_token_without_cookie(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/auth/telegram/miniapp",
        json={"init_data": build_init_data(bot_token="123456:test-token")},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert "set-cookie" not in response.headers


async def test_bad_init_data_returns_401(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/auth/telegram/miniapp", json={"init_data": "подделка"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Run: `uv run pytest backend/api/tests/test_auth_routes.py -v -m docker`
Expected: FAIL — маршрутов нет, ответ 404.

- [ ] **Шаг 3: Зависимости**

`deps.py`:

```python
"""Зависимости FastAPI: база, Valkey, текущий пользователь, роли."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from repibot_api.errors import ApiError
from repibot_core.db.engine import create_engine, create_session_factory
from repibot_core.db.models import UserRole
from repibot_core.security.tokens import TokenInvalidError, decode_access_token
from repibot_core.services.principal import Principal, PrincipalCache
from repibot_core.settings import Settings, get_settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Один движок на процесс: пул соединений создаётся однажды."""
    return create_engine(get_settings().database_url)


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return create_session_factory(get_engine())


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    return Redis.from_url(get_settings().valkey_url, decode_responses=False)


async def db_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


def get_principals(redis: Annotated[Redis, Depends(get_redis)]) -> PrincipalCache:
    return PrincipalCache(redis)


def settings_dep() -> Settings:
    return get_settings()


def client_ip(request: Request) -> str | None:
    """Адрес клиента.

    За nginx настоящий адрес приходит в X-Forwarded-For; берётся первый элемент —
    остальные дописаны промежуточными прокси и доверия не заслуживают.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@dataclass(frozen=True, slots=True)
class AuthContext:
    principal: Principal
    session_id: UUID


async def current_context(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> AuthContext:
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise ApiError("нужен токен доступа", 401, "unauthorized")

    try:
        claims = decode_access_token(
            header.removeprefix("Bearer "), secret=get_settings().jwt_secret.get_secret_value()
        )
    except TokenInvalidError as error:
        raise ApiError("токен недействителен", 401, "unauthorized") from error

    # Отзыв сессии действует немедленно: отметка в Valkey живёт ровно столько,
    # сколько остаётся жить выданному access-токену.
    if await principals.is_session_revoked(claims.session_id):
        raise ApiError("сессия отозвана", 401, "unauthorized")

    principal = await principals.get(session, claims.user_id)
    if principal is None:
        raise ApiError("пользователь не найден", 401, "unauthorized")
    if not principal.is_active:
        raise ApiError("аккаунт заблокирован", 403, "forbidden")

    return AuthContext(principal=principal, session_id=claims.session_id)


def require_role(*roles: UserRole) -> Callable[[AuthContext], AuthContext]:
    """Гейт по роли. Проверка всегда на бэкенде: скрытая кнопка — не защита."""

    def guard(context: Annotated[AuthContext, Depends(current_context)]) -> AuthContext:
        if context.principal.role not in roles:
            raise ApiError("недостаточно прав", 403, "forbidden")
        return context

    return guard
```

Заменить в `health.py` собственный `get_engine` на импорт из `deps`, чтобы в процессе не появлялось двух пулов соединений.

- [ ] **Шаг 4: Ошибки с заголовками и перевод кодов**

В `errors.py` расширить `ApiError` и `_error_response`:

```python
class ApiError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int,
        code: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        # Retry-After для 429: без него клиент не знает, когда повторить, и
        # повторяет немедленно.
        self.headers = headers or {}
```

В `_error_response` добавить параметр `extra_headers: dict[str, str] | None = None` и слить его в `headers`; в обработчике `ApiError` передавать `exc.headers`.

Там же — перевод ошибок сервисов в ответы:

```python
# Статус выбирается здесь, а не в сервисе: сервис знает, что произошло, а не
# как об этом принято сообщать по HTTP.
_AUTH_STATUS = {
    "invalid_credentials": 401,
    "unauthorized": 401,
    "email_not_verified": 403,
    "forbidden": 403,
    "not_found": 404,
    "email_taken": 409,
    "token_invalid": 400,
    "weak_password": 422,
    "validation_error": 422,
    "rate_limited": 429,
}


def api_error_from(error: AuthError) -> ApiError:
    return ApiError(str(error), _AUTH_STATUS.get(error.code, 400), error.code)
```

- [ ] **Шаг 5: Cookie и схемы**

`cookies.py`:

```python
"""Refresh-cookie. Её видит ровно один эндпоинт."""

from __future__ import annotations

from datetime import datetime

from fastapi import Response

REFRESH_COOKIE = "repibot_refresh"
# Путь ограничен единственным потребителем: браузер не пошлёт cookie ни на один
# другой эндпоинт, и поверхность CSRF сводится к одному методу.
COOKIE_PATH = "/api/auth/refresh"


def set_refresh_cookie(
    response: Response, token: str, *, expires_at: datetime, secure: bool
) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=COOKIE_PATH,
        expires=int(expires_at.timestamp()),
    )


def clear_refresh_cookie(response: Response, *, secure: bool) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        "",
        httponly=True,
        secure=secure,
        samesite="lax",
        path=COOKIE_PATH,
        max_age=0,
    )
```

`schemas.py`:

```python
"""Схемы запросов и ответов. Ровно то, что видит клиент."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from repibot_core.settings import Language


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    language: Language = "ru"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class EmailRequest(BaseModel):
    email: EmailStr


class TokenRequest(BaseModel):
    token: str = Field(min_length=1)


class PasswordResetRequest(BaseModel):
    token: str = Field(min_length=1)
    password: str = Field(min_length=1)


class MiniAppLoginRequest(BaseModel):
    init_data: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    expires_in: int


class AcceptedResponse(BaseModel):
    status: str


class MeResponse(BaseModel):
    id: int
    email: str | None
    email_verified: bool
    telegram_username: str | None
    name: str | None
    language: Language
    role: str
    referral_code: str
    has_password: bool
    has_telegram: bool
    passkey_count: int


class UpdateMeRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    language: Language


class SetPasswordRequest(BaseModel):
    current_password: str | None = None
    new_password: str = Field(min_length=1)


class ChangeEmailRequest(BaseModel):
    email: EmailStr


class SessionResponse(BaseModel):
    id: UUID
    user_agent: str | None
    ip: str | None
    created_at: datetime
    is_current: bool
```

`EmailStr` требует зависимость: в `backend/api/pyproject.toml` заменить `fastapi` на `fastapi` + `"email-validator>=2.2"`.

- [ ] **Шаг 6: Роутер входа**

`routers/auth.py`:

```python
"""Публичные эндпоинты входа.

Роутер разбирает запрос, вызывает сервис и раскладывает результат по ответу и
cookie. Решений здесь нет — они в services.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.cookies import REFRESH_COOKIE, clear_refresh_cookie, set_refresh_cookie
from repibot_api.deps import (
    AuthContext,
    client_ip,
    current_context,
    db_session,
    get_principals,
    get_redis,
)
from repibot_api.errors import ApiError, api_error_from
from repibot_api.origins import allowed_origins
from repibot_api.schemas import (
    AcceptedResponse,
    EmailRequest,
    LoginRequest,
    MiniAppLoginRequest,
    PasswordResetRequest,
    RegisterRequest,
    TokenRequest,
    TokenResponse,
)
from repibot_core.ratelimit import (
    LETTER_PER_EMAIL,
    LETTER_PER_IP,
    LOGIN_PER_EMAIL,
    LOGIN_PER_IP,
    MINIAPP_PER_IP,
    REGISTER_PER_IP,
    RateLimiter,
    Rule,
)
from repibot_core.services.auth.password import PasswordAuth
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.telegram import TelegramAuth
from repibot_core.services.auth.types import AuthError, IssuedSession
from repibot_core.services.principal import PrincipalCache
from repibot_core.settings import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _enforce(redis: Redis, key: str, rule: Rule) -> None:
    result = await RateLimiter(redis).hit(key, rule)
    if not result.allowed:
        raise ApiError(
            "слишком часто",
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            {"Retry-After": str(result.retry_after_seconds)},
        )


def _services(
    session: AsyncSession, principals: PrincipalCache
) -> tuple[AuthService, PasswordAuth, TelegramAuth]:
    settings = get_settings()
    auth = AuthService(session, settings, principals)
    return auth, PasswordAuth(session, settings, auth), TelegramAuth(session, settings, auth)


def _respond(response: Response, issued: IssuedSession) -> TokenResponse:
    if issued.refresh_token is not None and issued.refresh_expires_at is not None:
        set_refresh_cookie(
            response,
            issued.refresh_token,
            expires_at=issued.refresh_expires_at,
            secure=get_settings().environment == "production",
        )
    return TokenResponse(access_token=issued.access_token, expires_in=issued.access_expires_in)


@router.post("/register", status_code=202, response_model=AcceptedResponse)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AcceptedResponse:
    ip = client_ip(request)
    await _enforce(redis, f"register:ip:{ip}", REGISTER_PER_IP)

    _, letters, _ = _services(session, principals)
    try:
        await letters.register(
            email=payload.email, password=payload.password, language=payload.language
        )
    except AuthError as error:
        raise api_error_from(error) from error

    # Ответ одинаков и для нового адреса, и для повторной регистрации на
    # неподтверждённый: он не сообщает, есть ли такой аккаунт.
    return AcceptedResponse(status="verification_sent")


@router.post("/verify-email", response_model=TokenResponse)
async def verify_email(
    payload: TokenRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> TokenResponse:
    _, letters, _ = _services(session, principals)
    try:
        issued = await letters.verify_email(
            payload.token,
            user_agent=request.headers.get("user-agent"),
            ip=client_ip(request),
        )
    except AuthError as error:
        raise api_error_from(error) from error
    return _respond(response, issued)


@router.post("/resend-verification", status_code=202, response_model=AcceptedResponse)
async def resend_verification(
    payload: EmailRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AcceptedResponse:
    await _enforce(redis, f"letter:email:{payload.email}", LETTER_PER_EMAIL)
    await _enforce(redis, f"letter:ip:{client_ip(request)}", LETTER_PER_IP)

    _, letters, _ = _services(session, principals)
    await letters.resend_verification(payload.email)
    return AcceptedResponse(status="verification_sent")


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> TokenResponse:
    await _enforce(redis, f"login:ip:{client_ip(request)}", LOGIN_PER_IP)
    await _enforce(redis, f"login:email:{payload.email}", LOGIN_PER_EMAIL)

    _, letters, _ = _services(session, principals)
    try:
        issued = await letters.login(
            email=payload.email,
            password=payload.password,
            user_agent=request.headers.get("user-agent"),
            ip=client_ip(request),
        )
    except AuthError as error:
        raise api_error_from(error) from error
    return _respond(response, issued)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> TokenResponse:
    settings = get_settings()
    origin = request.headers.get("origin")
    # Этот эндпоинт — единственный, работающий по cookie, поэтому единственный,
    # которому нужна защита от межсайтовой подделки запроса.
    if origin is None or origin not in allowed_origins(
        settings.public_web_url, settings.public_app_url
    ):
        raise ApiError("origin не разрешён", 403, "forbidden")

    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise ApiError("нет refresh-токена", 401, "unauthorized")

    auth, _, _ = _services(session, principals)
    try:
        issued = await auth.refresh(
            token, user_agent=request.headers.get("user-agent"), ip=client_ip(request)
        )
    except AuthError as error:
        # Ротация не удалась — cookie гасится, иначе браузер будет повторять
        # запрос с мёртвым токеном до истечения срока.
        clear_refresh_cookie(response, secure=settings.environment == "production")
        raise api_error_from(error) from error
    return _respond(response, issued)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> None:
    auth, _, _ = _services(session, principals)
    await auth.logout(context.session_id)
    clear_refresh_cookie(response, secure=get_settings().environment == "production")


@router.post("/password/forgot", status_code=202, response_model=AcceptedResponse)
async def forgot_password(
    payload: EmailRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AcceptedResponse:
    await _enforce(redis, f"letter:email:{payload.email}", LETTER_PER_EMAIL)
    await _enforce(redis, f"letter:ip:{client_ip(request)}", LETTER_PER_IP)

    _, letters, _ = _services(session, principals)
    await letters.request_reset(payload.email)
    # Ответ одинаков для существующего и несуществующего адреса: иначе форма
    # превращается в проверку, зарегистрирован ли человек.
    return AcceptedResponse(status="reset_sent")


@router.post("/password/reset", response_model=TokenResponse)
async def reset_password(
    payload: PasswordResetRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> TokenResponse:
    _, letters, _ = _services(session, principals)
    try:
        issued = await letters.reset(
            payload.token,
            payload.password,
            user_agent=request.headers.get("user-agent"),
            ip=client_ip(request),
        )
    except AuthError as error:
        raise api_error_from(error) from error
    return _respond(response, issued)


@router.post("/email/change-confirm", status_code=204)
async def confirm_email_change(
    payload: TokenRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> None:
    """Подтверждение нового адреса.

    Эндпоинт публичный: письмо открывают в том браузере, где почта, а не в том,
    где открыт кабинет. Операцию авторизует сам токен.
    """
    _, letters, _ = _services(session, principals)
    try:
        await letters.apply_email_change(payload.token)
    except AuthError as error:
        raise api_error_from(error) from error


@router.post("/telegram/miniapp", response_model=TokenResponse)
async def login_from_miniapp(
    payload: MiniAppLoginRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> TokenResponse:
    await _enforce(redis, f"miniapp:ip:{client_ip(request)}", MINIAPP_PER_IP)

    _, _, telegram = _services(session, principals)
    try:
        issued = await telegram.login_from_miniapp(payload.init_data, ip=client_ip(request))
    except AuthError as error:
        raise api_error_from(error) from error
    return _respond(response, issued)
```

`allowed_origins` переезжает из `main.py` в новый модуль `backend/api/src/repibot_api/origins.py` — оставить её в `main` значило бы, что роутер импортирует `main`, а `main` импортирует роутер. `main.py` берёт её оттуда же; в `backend/api/tests/test_cors.py` правится только импорт.

- [ ] **Шаг 7: Подключить роутер и брокер**

В `main.py`: импортировать `allowed_origins` из `deps`, подключить `auth_router`, добавить жизненный цикл для брокера.

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Брокер поднимается вместе с приложением.

    api ставит задачу разбора outbox сразу после регистрации, а для этого
    брокеру нужно установленное соединение.
    """
    await broker.startup()
    try:
        yield
    finally:
        await broker.shutdown()
        await get_redis().aclose()
```

и `app = FastAPI(..., lifespan=lifespan)`.

- [ ] **Шаг 8: Убедиться, что тесты проходят**

Run: `uv run pytest backend/api -v -m docker`
Expected: PASS.

- [ ] **Шаг 9: Коммит**

```bash
git add backend/api backend/core/src/repibot_core/testing conftest.py
git commit -m "feat: эндпоинты регистрации, входа и обновления сессии"
```

---

## Задача 15: Профиль и админский гейт в API

**Файлы:**
- Создать: `backend/api/src/repibot_api/routers/me.py`, `routers/admin.py`
- Изменить: `backend/api/src/repibot_api/main.py`
- Тест: `backend/api/tests/test_me_routes.py`, `backend/api/tests/test_admin_routes.py`

**Интерфейсы:**
- Отдаёт: роутеры `me_router` (`/api/me`, `/api/me/sessions`, `/api/me/password`, `/api/me/email/change-request`) и `admin_router` (`/api/admin/whoami`).

- [ ] **Шаг 1: Написать падающий тест профиля**

```python
"""Профиль и сессии через API."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from repibot_core.testing.initdata import build_init_data

pytestmark = pytest.mark.docker


async def _miniapp_token(client: AsyncClient, telegram_id: int = 777) -> str:
    response = await client.post(
        "/api/auth/telegram/miniapp",
        json={"init_data": build_init_data(bot_token="123456:test-token", telegram_id=telegram_id)},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


async def test_me_requires_token(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_me_returns_profile(api_client: AsyncClient) -> None:
    token = await _miniapp_token(api_client)

    response = await api_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    body = response.json()
    assert response.status_code == 200
    assert body["has_telegram"] is True
    assert body["has_password"] is False
    assert body["email"] is None
    assert body["role"] == "user"


async def test_language_is_updated(api_client: AsyncClient) -> None:
    token = await _miniapp_token(api_client)

    response = await api_client.patch(
        "/api/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Иван", "language": "en"},
    )

    assert response.status_code == 200
    assert response.json()["language"] == "en"


async def test_first_password_is_set_without_current(api_client: AsyncClient) -> None:
    """У вошедшего через Telegram пароля нет — спрашивать текущий не с чего."""
    token = await _miniapp_token(api_client)

    response = await api_client.post(
        "/api/me/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"new_password": "совершенно обычный пароль"},
    )

    assert response.status_code == 204


async def test_sessions_are_listed_and_revoked(api_client: AsyncClient) -> None:
    token = await _miniapp_token(api_client)
    other = await _miniapp_token(api_client)  # второе открытие MiniApp — вторая сессия
    headers = {"Authorization": f"Bearer {token}"}

    listed = await api_client.get("/api/me/sessions", headers=headers)
    assert listed.status_code == 200
    sessions = listed.json()
    assert len(sessions) == 2
    assert [item["is_current"] for item in sessions].count(True) == 1

    victim = next(item["id"] for item in sessions if not item["is_current"])
    revoked = await api_client.delete(f"/api/me/sessions/{victim}", headers=headers)
    assert revoked.status_code == 204

    # Отозванная сессия перестаёт работать немедленно, а не через 15 минут.
    denied = await api_client.get("/api/me", headers={"Authorization": f"Bearer {other}"})
    assert denied.status_code == 401


async def test_session_of_another_user_cannot_be_revoked(api_client: AsyncClient) -> None:
    mine = await _miniapp_token(api_client, telegram_id=777)
    stranger = await _miniapp_token(api_client, telegram_id=888)

    listed = await api_client.get(
        "/api/me/sessions", headers={"Authorization": f"Bearer {stranger}"}
    )
    victim = listed.json()[0]["id"]

    response = await api_client.delete(
        f"/api/me/sessions/{victim}", headers={"Authorization": f"Bearer {mine}"}
    )

    assert response.status_code == 404
```

- [ ] **Шаг 2: Написать падающий тест админского гейта**

```python
"""Гейт роли. Страницы админки — подпроект 5, проверяется сам гейт."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from repibot_core.settings import get_settings
from repibot_core.testing.initdata import build_init_data

pytestmark = pytest.mark.docker


async def test_regular_user_is_refused(api_client: AsyncClient) -> None:
    login = await api_client.post(
        "/api/auth/telegram/miniapp",
        json={"init_data": build_init_data(bot_token="123456:test-token", telegram_id=555)},
    )
    token = login.json()["access_token"]

    response = await api_client.get(
        "/api/admin/whoami", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_admin_from_env_passes_the_gate(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "999")
    get_settings.cache_clear()

    login = await api_client.post(
        "/api/auth/telegram/miniapp",
        json={"init_data": build_init_data(bot_token="123456:test-token", telegram_id=999)},
    )
    token = login.json()["access_token"]

    response = await api_client.get(
        "/api/admin/whoami", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"

    get_settings.cache_clear()


async def test_gate_without_token_is_401(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/admin/whoami")

    assert response.status_code == 401
```

- [ ] **Шаг 3: Убедиться, что тесты падают**

Run: `uv run pytest backend/api/tests/test_me_routes.py backend/api/tests/test_admin_routes.py -v -m docker`
Expected: FAIL — 404 на всех маршрутах.

- [ ] **Шаг 4: Роутер профиля**

`routers/me.py`:

```python
"""Профиль и сессии текущего пользователя."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import (
    AuthContext,
    client_ip,
    current_context,
    db_session,
    get_principals,
    get_redis,
)
from repibot_api.errors import api_error_from
from repibot_api.schemas import (
    AcceptedResponse,
    ChangeEmailRequest,
    MeResponse,
    SessionResponse,
    SetPasswordRequest,
    UpdateMeRequest,
)
from repibot_core.ratelimit import LETTER_PER_EMAIL, RateLimiter
from repibot_core.services.auth.password import PasswordAuth
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError
from repibot_core.services.principal import PrincipalCache
from repibot_core.services.profile import ProfileService, ProfileView
from repibot_core.settings import get_settings

router = APIRouter(prefix="/api/me", tags=["me"])


def _profile(session: AsyncSession, principals: PrincipalCache) -> ProfileService:
    settings = get_settings()
    auth = AuthService(session, settings, principals)
    return ProfileService(session, settings, auth, principals, PasswordAuth(session, settings, auth))


def _to_response(view: ProfileView) -> MeResponse:
    return MeResponse(
        id=view.user_id,
        email=view.email,
        email_verified=view.email_verified,
        telegram_username=view.telegram_username,
        name=view.name,
        language=view.language,  # type: ignore[arg-type]
        role=view.role.value,
        referral_code=view.referral_code,
        has_password=view.has_password,
        has_telegram=view.has_telegram,
        passkey_count=view.passkey_count,
    )


@router.get("", response_model=MeResponse)
async def read_me(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> MeResponse:
    try:
        return _to_response(await _profile(session, principals).view(context.principal.user_id))
    except AuthError as error:
        raise api_error_from(error) from error


@router.patch("", response_model=MeResponse)
async def update_me(
    payload: UpdateMeRequest,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> MeResponse:
    try:
        view = await _profile(session, principals).update(
            context.principal.user_id, name=payload.name, language=payload.language
        )
    except AuthError as error:
        raise api_error_from(error) from error
    return _to_response(view)


@router.post("/password", status_code=204)
async def set_password(
    payload: SetPasswordRequest,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> None:
    try:
        await _profile(session, principals).set_password(
            context.principal.user_id,
            current=payload.current_password,
            new=payload.new_password,
        )
    except AuthError as error:
        raise api_error_from(error) from error


@router.post("/email/change-request", status_code=202, response_model=AcceptedResponse)
async def request_email_change(
    payload: ChangeEmailRequest,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AcceptedResponse:
    result = await RateLimiter(redis).hit(f"letter:email:{payload.email}", LETTER_PER_EMAIL)
    if not result.allowed:
        from repibot_api.errors import ApiError

        raise ApiError(
            "слишком часто",
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            {"Retry-After": str(result.retry_after_seconds)},
        )

    try:
        await _profile(session, principals).request_email_change(
            context.principal.user_id, payload.email
        )
    except AuthError as error:
        raise api_error_from(error) from error
    return AcceptedResponse(status="confirmation_sent")


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> list[SessionResponse]:
    items = await _profile(session, principals).list_sessions(
        context.principal.user_id, context.session_id
    )
    return [
        SessionResponse(
            id=item.session_id,
            user_agent=item.user_agent,
            ip=item.ip,
            created_at=item.created_at,
            is_current=item.is_current,
        )
        for item in items
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> None:
    auth = AuthService(session, get_settings(), principals)
    try:
        await auth.revoke_session(context.principal.user_id, session_id)
    except AuthError as error:
        raise api_error_from(error) from error


@router.delete("/sessions", status_code=204)
async def revoke_other_sessions(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> None:
    auth = AuthService(session, get_settings(), principals)
    await auth.revoke_other_sessions(context.principal.user_id, context.session_id)
```

Неиспользуемые импорты (`client_ip`, `Request`) убрать, если линтер укажет.

- [ ] **Шаг 5: Роутер админского гейта**

`routers/admin.py`:

```python
"""Административные маршруты.

Пока здесь только проверка гейта: страницы админки появятся в подпроекте 5.
Гейт написан и покрыт тестом сразу, чтобы к моменту появления страниц не
пришлось решать вопрос доступа задним числом.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from repibot_api.deps import AuthContext, require_role
from repibot_core.db.models import UserRole

router = APIRouter(prefix="/api/admin", tags=["admin"])


class WhoAmIResponse(BaseModel):
    id: int
    role: str


@router.get("/whoami", response_model=WhoAmIResponse)
async def whoami(
    context: Annotated[AuthContext, Depends(require_role(UserRole.admin, UserRole.support))],
) -> WhoAmIResponse:
    return WhoAmIResponse(id=context.principal.user_id, role=context.principal.role.value)
```

- [ ] **Шаг 6: Подключить роутеры**

В `main.py` заменить пустые `client_router` и `admin_router` на подключение реальных: `app.include_router(auth_router)`, `app.include_router(me_router)`, `app.include_router(admin_router)`. Пустые заготовки удалить вместе с их упоминанием в тестах.

- [ ] **Шаг 7: Убедиться, что тесты проходят**

Run: `uv run pytest backend/api -v -m docker` затем `uv run check`
Expected: PASS.

- [ ] **Шаг 8: Коммит**

```bash
git add backend/api
git commit -m "feat: профиль, список сессий и гейт роли в API"
```

---

## Задача 16: Бот — регистрация по `/start` и выбор языка

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/telegram_users.py`
- Создать: `backend/bot/src/repibot_bot/middleware.py`, `backend/bot/src/repibot_bot/handlers/language.py`
- Изменить: `backend/bot/src/repibot_bot/handlers/start.py`, `backend/bot/src/repibot_bot/main.py`
- Тест: `backend/bot/tests/test_start.py`, `backend/bot/tests/test_language.py`, `backend/core/tests/test_telegram_users.py`

**Интерфейсы:**
- Отдаёт: `TelegramUserService(session, settings)` с методами `ensure(telegram_id, *, username, first_name, language_code) -> User` и `set_language(telegram_id, language) -> None`; `UserMiddleware` (aiogram) — кладёт в данные хендлера `user` и `language`; `build_language_router()`.

- [ ] **Шаг 1: Написать падающий тест сервиса**

```python
"""Создание пользователя по обращению в бот."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.users import UserRepository
from repibot_core.services.telegram_users import TelegramUserService
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker


async def test_first_start_creates_user(db_session: AsyncSession) -> None:
    service = TelegramUserService(db_session, get_settings())

    user = await service.ensure(777, username="ivan", first_name="Иван", language_code="ru")

    assert user.telegram_id == 777
    assert user.language == "ru"
    assert user.referral_code


async def test_second_start_returns_the_same_user(db_session: AsyncSession) -> None:
    service = TelegramUserService(db_session, get_settings())
    first = await service.ensure(777, username="ivan", first_name="Иван", language_code="ru")

    second = await service.ensure(777, username="ivan_new", first_name="Иван", language_code="ru")

    assert second.id == first.id
    assert second.telegram_username == "ivan_new"


async def test_unsupported_language_falls_back(db_session: AsyncSession) -> None:
    service = TelegramUserService(db_session, get_settings())

    user = await service.ensure(778, username=None, first_name="Hans", language_code="de")

    assert user.language == get_settings().default_language


async def test_language_is_saved(db_session: AsyncSession) -> None:
    service = TelegramUserService(db_session, get_settings())
    await service.ensure(779, username=None, first_name=None, language_code="ru")

    await service.set_language(779, "en")

    user = await UserRepository(db_session).get_by_telegram_id(779)
    assert user is not None
    assert user.language == "en"
```

- [ ] **Шаг 2: Написать падающий тест хендлеров**

Дополнить `backend/bot/tests/test_start.py`:

```python
async def test_start_offers_the_app() -> None:
    """Кнопка запуска MiniApp — единственный вход в магазин из бота."""
    message = MagicMock()
    message.answer = AsyncMock()

    await handle_start(message, user=MagicMock(name="Иван"), language="ru")

    markup = message.answer.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].web_app is not None


async def test_start_answers_in_user_language() -> None:
    message = MagicMock()
    message.answer = AsyncMock()

    await handle_start(message, user=MagicMock(), language="en")

    assert "Hello" in message.answer.await_args.args[0]
```

Создать `backend/bot/tests/test_language.py`:

```python
"""Выбор языка кнопками."""

from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.storage.memory import MemoryStorage

from repibot_bot.handlers.language import handle_language, handle_language_choice
from repibot_bot.main import build_dispatcher


async def test_language_command_shows_options() -> None:
    message = MagicMock()
    message.answer = AsyncMock()

    await handle_language(message, language="ru")

    markup = message.answer.await_args.kwargs["reply_markup"]
    codes = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert codes == ["lang:ru", "lang:en"]


async def test_choice_saves_language() -> None:
    callback = MagicMock()
    callback.data = "lang:en"
    callback.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.from_user.id = 777
    service = AsyncMock()

    await handle_language_choice(callback, telegram_users=service)

    service.set_language.assert_awaited_once_with(777, "en")
    assert "Language" in callback.message.edit_text.await_args.args[0]


def test_dispatcher_registers_language_router() -> None:
    dispatcher = build_dispatcher(MemoryStorage())

    assert any(router.name == "language" for router in dispatcher.sub_routers)
```

- [ ] **Шаг 3: Убедиться, что тесты падают**

Run: `uv run pytest backend/bot backend/core/tests/test_telegram_users.py -v -m docker`
Expected: FAIL.

- [ ] **Шаг 4: Сервис пользователей Telegram**

```python
"""Пользователь, пришедший в бот.

Отдельно от services/auth/telegram.py: там вход с выдачей токенов, здесь —
обслуживание диалога в боте, где токены не нужны вовсе.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.db.repositories.users import UserRepository
from repibot_core.settings import Settings


class TelegramUserService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._users = UserRepository(session)

    async def ensure(
        self,
        telegram_id: int,
        *,
        username: str | None,
        first_name: str | None,
        language_code: str | None,
    ) -> User:
        """Находит или создаёт пользователя.

        Написавший боту — уже пользователь: без записи в базе ему нельзя ни
        выбрать язык, ни получить уведомление.
        """
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is not None:
            user.telegram_username = username
            if user.name is None:
                user.name = first_name
            await self._session.commit()
            return user

        user = await self._users.create(
            telegram_id=telegram_id,
            telegram_username=username,
            name=first_name,
            language=self._language(language_code),
            referral_code=await self._users.next_referral_code(),
        )
        await self._session.commit()
        return user

    async def set_language(self, telegram_id: int, language: str) -> None:
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is None:
            return
        user.language = language
        await self._session.commit()

    def _language(self, code: str | None) -> str:
        if code is None:
            return self._settings.default_language
        short = code.split("-")[0]
        return (
            short
            if short in self._settings.supported_languages
            else self._settings.default_language
        )
```

- [ ] **Шаг 5: Middleware бота**

`backend/bot/src/repibot_bot/middleware.py`:

```python
"""Подстановка пользователя и его языка до вызова хендлера.

Хендлер не должен открывать сессию базы и разбираться, кто перед ним: иначе
это повторяется в каждом обработчике, и в одном из них забудется.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from repibot_core.db.engine import create_engine, create_session_factory
from repibot_core.services.telegram_users import TelegramUserService
from repibot_core.settings import get_settings


class UserMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        settings = get_settings()
        # Движок один на процесс: создавать его на каждое сообщение значит
        # открывать новый пул соединений на каждое сообщение.
        self._factory = create_session_factory(create_engine(settings.database_url))
        self._settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        sender = event.from_user if isinstance(event, Message | CallbackQuery) else None
        if sender is None:
            return await handler(event, data)

        async with self._factory() as session:
            service = TelegramUserService(session, self._settings)
            user = await service.ensure(
                sender.id,
                username=sender.username,
                first_name=sender.first_name,
                language_code=sender.language_code,
            )
            data["user"] = user
            data["language"] = user.language
            data["telegram_users"] = service
            return await handler(event, data)
```

- [ ] **Шаг 6: Хендлеры**

`handlers/start.py`:

```python
"""Приветствие и кнопка запуска MiniApp."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from repibot_core.db.models import User
from repibot_core.i18n import translate
from repibot_core.settings import get_settings


async def handle_start(message: Message, user: User, language: str) -> None:
    name = user.name or (message.from_user.full_name if message.from_user else "")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "bot.start.open_app"),
                    web_app=WebAppInfo(url=get_settings().public_app_url),
                )
            ]
        ]
    )
    await message.answer(
        translate(language, "bot.start.greeting", name=name), reply_markup=keyboard
    )


def build_start_router() -> Router:
    """Новый роутер на каждый вызов.

    aiogram запрещает подключать один экземпляр Router к двум диспетчерам,
    а модульный синглтон делает второй Dispatcher в процессе невозможным.
    """
    router = Router(name="start")
    router.message.register(handle_start, CommandStart())
    return router
```

`handlers/language.py`:

```python
"""Переключение языка."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from repibot_core.i18n import translate
from repibot_core.services.telegram_users import TelegramUserService

_TITLES = {"ru": "Русский", "en": "English"}


async def handle_language(message: Message, language: str) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=title, callback_data=f"lang:{code}")]
            for code, title in _TITLES.items()
        ]
    )
    await message.answer(translate(language, "bot.language.choose"), reply_markup=keyboard)


async def handle_language_choice(
    callback: CallbackQuery, telegram_users: TelegramUserService
) -> None:
    chosen = (callback.data or "").removeprefix("lang:")
    if chosen not in _TITLES:
        await callback.answer()
        return

    await telegram_users.set_language(callback.from_user.id, chosen)
    # Подтверждение приходит уже на новом языке: иначе непонятно, сработало ли.
    if callback.message is not None:
        await callback.message.edit_text(translate(chosen, "bot.language.saved"))
    await callback.answer()


def build_language_router() -> Router:
    router = Router(name="language")
    router.message.register(handle_language, Command("language"))
    router.callback_query.register(handle_language_choice, F.data.startswith("lang:"))
    return router
```

В `main.py` в `build_dispatcher` добавить `UserMiddleware` на сообщения и колбэки и подключить второй роутер:

```python
def build_dispatcher(storage: BaseStorage) -> Dispatcher:
    dispatcher = Dispatcher(storage=storage)
    middleware = UserMiddleware()
    dispatcher.message.middleware(middleware)
    dispatcher.callback_query.middleware(middleware)
    dispatcher.include_router(build_start_router())
    dispatcher.include_router(build_language_router())
    return dispatcher
```

- [ ] **Шаг 7: Убедиться, что тесты проходят**

Run: `uv run pytest backend/bot backend/core/tests/test_telegram_users.py -v -m docker`
Expected: PASS.

Тест `test_start_survives_missing_from_user` из подпроекта 0 удаляется: сообщение без `from_user` теперь до хендлера не доходит — middleware пропускает его дальше без `user`, а фильтр `CommandStart` без пользователя не срабатывает. Вместо него добавляется тест middleware:

```python
async def test_middleware_passes_through_events_without_sender() -> None:
    """Сообщения от каналов приходят без from_user — падать на этом нельзя."""
    middleware = UserMiddleware()
    handler = AsyncMock()
    event = MagicMock(spec=Message)
    event.from_user = None

    await middleware(handler, event, {})

    handler.assert_awaited_once()
```

- [ ] **Шаг 8: Коммит**

```bash
git add backend/bot backend/core/src/repibot_core/services/telegram_users.py backend/core/tests/test_telegram_users.py
git commit -m "feat: бот создаёт пользователя и переключает язык"
```

---

## Задача 17: Синхронизация типов API

**Файлы:**
- Изменить: `frontend/packages/core/src/api/openapi.json`, `frontend/packages/core/src/api/schema.d.ts`

**Интерфейсы:**
- Отдаёт: типы `paths` с новыми маршрутами — их используют задачи 18–20.

- [ ] **Шаг 1: Перегенерировать схему**

```bash
uv run export-openapi
cd frontend && pnpm --filter @repibot/core generate:api && cd ..
```

Точные команды — в `package.json` пакета `@repibot/core` (скрипт добавлен в подпроекте 0).

- [ ] **Шаг 2: Проверить, что расхождений не осталось**

Run: `uv run verify-generated`
Expected: расхождений нет. Если проверка падает — сгенерированные файлы правятся генератором, а не руками.

- [ ] **Шаг 3: Убедиться, что типы собираются**

Run: `cd frontend && pnpm -r exec tsc --noEmit && cd ..`
Expected: без ошибок.

- [ ] **Шаг 4: Коммит**

```bash
git add frontend/packages/core/src/api
git commit -m "chore: типы API после добавления эндпоинтов входа"
```

---

## Задача 18: Клиентская часть аутентификации

**Файлы:**
- Создать: `frontend/packages/core/src/auth/store.ts`, `client.ts`, `hooks.ts`, `schemas.ts`
- Изменить: `frontend/packages/core/src/index.ts`, `frontend/packages/core/src/i18n/ru.ts`, `en.ts`
- Тест: `frontend/packages/core/src/auth/client.test.ts`, `store.test.ts`, `schemas.test.ts`

**Интерфейсы:**
- Отдаёт: `createTokenStore()` → `{ get(): string | null, set(token: string | null): void, subscribe(fn): () => void }`; `createAuthClient({ baseUrl, store, onSignedOut })` → `{ api, refresh(): Promise<boolean>, signOut(): Promise<void> }`; хуки `useMe()`, `useLogin()`, `useRegister()`, `useLogout()`, `useUpdateProfile()`, `useSessions()`, `useRevokeSession()`; схемы `loginSchema`, `registerSchema`, `resetSchema`, `emailSchema`, `passwordSchema`; `errorMessageKey(code: string): TranslationKey`.

- [ ] **Шаг 1: Написать падающий тест хранилища и клиента**

`store.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest'

import { createTokenStore } from './store'

describe('createTokenStore', () => {
  it('хранит токен только в памяти', () => {
    const store = createTokenStore()

    store.set('token')

    expect(store.get()).toBe('token')
    // Ни localStorage, ни sessionStorage: в веб-версии Telegram чужой контекст,
    // а XSS достаёт оттуда токен одной строкой.
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('уведомляет подписчиков о смене', () => {
    const store = createTokenStore()
    const listener = vi.fn()
    store.subscribe(listener)

    store.set('token')
    store.set(null)

    expect(listener).toHaveBeenCalledTimes(2)
  })
})
```

`client.test.ts` (дополнить существующий файл):

```ts
describe('createAuthClient', () => {
  it('обновляет токен один раз на несколько параллельных 401', async () => {
    let refreshCalls = 0
    const fetchMock = vi.fn(async (request: Request) => {
      if (request.url.endsWith('/api/auth/refresh')) {
        refreshCalls += 1
        return Response.json({ access_token: 'fresh', expires_in: 900 })
      }
      const auth = request.headers.get('Authorization')
      if (auth !== 'Bearer fresh') {
        return Response.json({ error: { code: 'unauthorized' } }, { status: 401 })
      }
      return Response.json({ id: 1 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = createTokenStore()
    store.set('stale')
    const client = createAuthClient({ baseUrl: 'https://api.test', store })

    const results = await Promise.all([
      client.api.GET('/api/me'),
      client.api.GET('/api/me'),
      client.api.GET('/api/me'),
    ])

    // Один refresh на три запроса: иначе три вкладки ротируют токен друг под
    // другом и выбивают сессию.
    expect(refreshCalls).toBe(1)
    expect(results.every((result) => result.data !== undefined)).toBe(true)
  })

  it('сообщает о выходе, когда обновление не удалось', async () => {
    const onSignedOut = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ error: { code: 'unauthorized' } }, { status: 401 })),
    )
    const store = createTokenStore()
    store.set('stale')
    const client = createAuthClient({ baseUrl: 'https://api.test', store, onSignedOut })

    await client.api.GET('/api/me')

    expect(onSignedOut).toHaveBeenCalledOnce()
    expect(store.get()).toBeNull()
  })

  it('не пытается обновиться в ответ на 401 самого обновления', async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({ error: { code: 'unauthorized' } }, { status: 401 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const client = createAuthClient({ baseUrl: 'https://api.test', store: createTokenStore() })

    await client.refresh()

    expect(fetchMock).toHaveBeenCalledOnce()
  })
})
```

`schemas.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { loginSchema, registerSchema } from './schemas'

describe('схемы форм', () => {
  it('требует корректный адрес', () => {
    expect(loginSchema.safeParse({ email: 'не адрес', password: 'длинный пароль' }).success).toBe(
      false,
    )
  })

  it('требует пароль от десяти символов — как и бэкенд', () => {
    const result = registerSchema.safeParse({
      email: 'user@example.org',
      password: 'короткий',
      language: 'ru',
    })

    expect(result.success).toBe(false)
  })

  it('принимает валидную регистрацию', () => {
    const result = registerSchema.safeParse({
      email: 'user@example.org',
      password: 'совершенно обычный пароль',
      language: 'ru',
    })

    expect(result.success).toBe(true)
  })
})
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Run: `cd frontend && pnpm --filter @repibot/core test && cd ..`
Expected: FAIL — модулей нет.

- [ ] **Шаг 3: Хранилище токена**

```ts
/**
 * Access-токен живёт в памяти и нигде больше.
 *
 * localStorage отпадает по двум причинам: в веб-версии Telegram наш домен
 * оказывается в стороннем контексте, а любая XSS читает его одной строкой.
 * Плата за это — перезагрузка страницы теряет токен и вызывает refresh.
 */
export interface TokenStore {
  get(): string | null
  set(token: string | null): void
  subscribe(listener: () => void): () => void
}

export function createTokenStore(): TokenStore {
  let token: string | null = null
  const listeners = new Set<() => void>()

  return {
    get: () => token,
    set(next) {
      token = next
      for (const listener of listeners) listener()
    },
    subscribe(listener) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
  }
}
```

- [ ] **Шаг 4: Клиент с обновлением токена**

```ts
import createClient, { type Middleware } from 'openapi-fetch'

import type { paths } from '../api/schema'
import type { TokenStore } from './store'

const REFRESH_PATH = '/api/auth/refresh'

export interface AuthClientOptions {
  baseUrl: string
  store: TokenStore
  onSignedOut?: () => void
}

/**
 * Клиент API, умеющий обновлять просроченный access-токен.
 *
 * Обновление single-flight: параллельные запросы ждут один и тот же вызов
 * refresh. Иначе каждый из них ротирует токен, и сервер, увидев повторное
 * использование предыдущего, отзовёт сессию целиком.
 */
export function createAuthClient({ baseUrl, store, onSignedOut }: AuthClientOptions) {
  const client = createClient<paths>({ baseUrl, credentials: 'include' })
  let inFlight: Promise<boolean> | null = null

  async function refresh(): Promise<boolean> {
    const response = await fetch(`${baseUrl}${REFRESH_PATH}`, {
      method: 'POST',
      credentials: 'include',
    })
    if (!response.ok) {
      store.set(null)
      onSignedOut?.()
      return false
    }
    const body = (await response.json()) as { access_token: string }
    store.set(body.access_token)
    return true
  }

  function refreshOnce(): Promise<boolean> {
    inFlight ??= refresh().finally(() => {
      inFlight = null
    })
    return inFlight
  }

  const auth: Middleware = {
    async onRequest({ request }) {
      const token = store.get()
      if (token) request.headers.set('Authorization', `Bearer ${token}`)
      return request
    },
    async onResponse({ request, response }) {
      // Ответ 401 самого обновления обрабатывать нечем: рекурсия здесь дала бы
      // бесконечный цикл запросов.
      if (response.status !== 401 || request.url.endsWith(REFRESH_PATH)) return response
      if (!(await refreshOnce())) return response

      const retry = new Request(request, {
        headers: new Headers(request.headers),
      })
      retry.headers.set('Authorization', `Bearer ${store.get() ?? ''}`)
      return fetch(retry)
    },
  }

  client.use(auth)

  return {
    api: client,
    refresh: refreshOnce,
    async signOut() {
      await client.POST('/api/auth/logout')
      store.set(null)
      onSignedOut?.()
    },
  }
}
```

- [ ] **Шаг 5: Схемы форм и коды ошибок**

`schemas.ts`:

```ts
import { z } from 'zod'

// Минимальная длина совпадает с политикой бэкенда: разошлись бы значения —
// форма отправляла бы заведомо отклоняемые пароли.
const password = z.string().min(10)

export const emailSchema = z.object({ email: z.string().email() })
export const passwordSchema = z.object({ password })
export const loginSchema = z.object({ email: z.string().email(), password: z.string().min(1) })
export const registerSchema = z.object({
  email: z.string().email(),
  password,
  language: z.enum(['ru', 'en']),
})
export const resetSchema = z.object({ token: z.string().min(1), password })

export type LoginInput = z.infer<typeof loginSchema>
export type RegisterInput = z.infer<typeof registerSchema>
```

Добавить в `i18n/ru.ts` и `en.ts` ключи: `auth.error.invalid_credentials`, `auth.error.email_not_verified`, `auth.error.email_taken`, `auth.error.weak_password`, `auth.error.token_invalid`, `auth.error.rate_limited`, `auth.error.unknown`, а также подписи форм (`auth.login.title`, `auth.login.submit`, `auth.register.title`, `auth.register.submit`, `auth.forgot.title`, `auth.reset.title`, `auth.verify.pending`, `auth.verify.resend`, `account.title`, `account.security`, `account.sessions`, `account.password`, `account.email`, `account.language`, `account.logout`, `account.revoke`, `account.current_session`).

`errorMessageKey` переводит код ответа в ключ словаря, незнакомый код — в `auth.error.unknown`: новый код на бэкенде не должен показывать пользователю пустоту.

- [ ] **Шаг 6: Хуки и контекст**

`hooks.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, type ReactNode, useContext, useMemo } from 'react'

import { translate, type Language, type TranslationKey } from '../i18n/index'
import { createAuthClient } from './client'
import { createTokenStore } from './store'

type AuthClient = ReturnType<typeof createAuthClient>

const AuthContext = createContext<AuthClient | null>(null)

export interface AuthProviderProps {
  children: ReactNode
  baseUrl?: string
  onSignedOut?: () => void
}

/**
 * Один клиент на приложение.
 *
 * Базовый URL по умолчанию пустой: веб, MiniApp и API стоят за одним nginx, и
 * абсолютный адрес в сборке потребовал бы пересборки под каждое развёртывание.
 */
export function AuthProvider({ children, baseUrl = '', onSignedOut }: AuthProviderProps) {
  const client = useMemo(
    () => createAuthClient({ baseUrl, store: createTokenStore(), onSignedOut }),
    [baseUrl, onSignedOut],
  )
  return <AuthContext.Provider value={client}>{children}</AuthContext.Provider>
}

export function useAuthClient(): AuthClient {
  const client = useContext(AuthContext)
  if (client === null) throw new Error('AuthProvider не подключён')
  return client
}

/** Код ошибки бэкенда → ключ словаря. Незнакомый код не должен давать пустоту. */
export function errorMessageKey(code: string | undefined): TranslationKey {
  const known: Record<string, TranslationKey> = {
    invalid_credentials: 'auth.error.invalid_credentials',
    email_not_verified: 'auth.error.email_not_verified',
    email_taken: 'auth.error.email_taken',
    weak_password: 'auth.error.weak_password',
    token_invalid: 'auth.error.token_invalid',
    rate_limited: 'auth.error.rate_limited',
  }
  return (code && known[code]) || 'auth.error.unknown'
}

function messageFrom(error: unknown, language: Language): string {
  const code = (error as { error?: { code?: string } })?.error?.code
  return translate(language, errorMessageKey(code))
}

export function useMe() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me')
      if (error) throw error
      return data
    },
  })
}

export function useLogin(language: Language) {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (input: { email: string; password: string }) => {
      const { data, error } = await api.POST('/api/auth/login', { body: input })
      if (error) throw new Error(messageFrom(error, language))
      return data
    },
    // Профиль перезапрашивается после входа: прежний ответ относится к другому
    // пользователю или к его отсутствию.
    onSuccess: () => queries.invalidateQueries({ queryKey: ['me'] }),
  })
}

export function useRegister(language: Language) {
  const { api } = useAuthClient()
  return useMutation({
    mutationFn: async (input: { email: string; password: string; language: Language }) => {
      const { data, error } = await api.POST('/api/auth/register', { body: input })
      if (error) throw new Error(messageFrom(error, language))
      return data
    },
  })
}

export function useLogout() {
  const client = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: () => client.signOut(),
    onSuccess: () => queries.clear(),
  })
}

export function useUpdateProfile(language: Language) {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (input: { name: string | null; language: Language }) => {
      const { data, error } = await api.PATCH('/api/me', { body: input })
      if (error) throw new Error(messageFrom(error, language))
      return data
    },
    onSuccess: (data) => queries.setQueryData(['me'], data),
  })
}

export function useSessions() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['sessions'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me/sessions')
      if (error) throw error
      return data
    },
  })
}

export function useRevokeSession(language: Language) {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/me/sessions/{session_id}', {
        params: { path: { session_id: id } },
      })
      if (error) throw new Error(messageFrom(error, language))
    },
    onSuccess: () => queries.invalidateQueries({ queryKey: ['sessions'] }),
  })
}
```

Файл с расширением `.tsx`, а не `.ts`: в нём есть разметка провайдера. `index.ts` пакета экспортирует всё перечисленное в блоке интерфейсов.

- [ ] **Шаг 7: Убедиться, что тесты проходят**

Run: `cd frontend && pnpm --filter @repibot/core test && pnpm -r exec tsc --noEmit && cd ..`
Expected: PASS.

- [ ] **Шаг 8: Коммит**

```bash
git add frontend/packages/core
git commit -m "feat: клиентская аутентификация с обновлением токена"
```

---

## Задача 19: Экраны веб-кабинета

**Файлы:**
- Создать: `frontend/apps/web/src/app/(auth)/login/page.tsx`, `register/page.tsx`, `verify-email/page.tsx`, `forgot-password/page.tsx`, `reset-password/page.tsx`, `(auth)/layout.tsx`
- Создать: `frontend/apps/web/src/app/account/page.tsx`, `account/layout.tsx`, `account/security/page.tsx`, `(auth)/confirm-email/page.tsx`
- Создать: `frontend/apps/web/src/components/auth-provider.tsx`, `auth-guard.tsx`
- Создать в `frontend/packages/ui/src/components/`: `form-field.tsx`, `password-input.tsx`, `dialog.tsx`, `empty-state.tsx`, `switch.tsx`
- Тест: `frontend/apps/web/src/app/(auth)/login/page.test.tsx`, `frontend/apps/web/src/components/auth-guard.test.tsx`, тесты новых компонентов `ui`

**Интерфейсы:**
- Отдаёт: `AuthProvider` (клиентский компонент с `AuthClient` и `QueryClient`), `AuthGuard` (редирект на `/login` без токена), страницы маршрутов.

- [ ] **Шаг 1: Написать падающий тест формы входа**

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import LoginPage from './page'

describe('страница входа', () => {
  it('показывает ошибку формы до отправки запроса', async () => {
    const user = userEvent.setup()
    render(<LoginPage />)

    await user.type(screen.getByLabelText(/почта|email/i), 'не адрес')
    await user.click(screen.getByRole('button', { name: /войти|sign in/i }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('переводит код ошибки бэкенда во внятную фразу', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({ error: { code: 'invalid_credentials' } }, { status: 401 }),
      ),
    )
    const user = userEvent.setup()
    render(<LoginPage />)

    await user.type(screen.getByLabelText(/почта|email/i), 'user@example.org')
    await user.type(screen.getByLabelText(/пароль|password/i), 'совершенно обычный пароль')
    await user.click(screen.getByRole('button', { name: /войти|sign in/i }))

    await waitFor(() => {
      // Пользователь видит фразу, а не код: код — контракт для фронтенда.
      expect(screen.getByRole('alert').textContent).not.toContain('invalid_credentials')
    })
  })
})
```

Тест гейта:

```tsx
describe('AuthGuard', () => {
  it('уводит на вход, когда обновление токена не удалось', async () => {
    const replace = vi.fn()
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 401 })))

    render(
      <AuthGuard router={{ replace }}>
        <p>кабинет</p>
      </AuthGuard>,
    )

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/login'))
    expect(screen.queryByText('кабинет')).not.toBeInTheDocument()
  })
})
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Run: `cd frontend && pnpm --filter @repibot/web test && cd ..`
Expected: FAIL — страниц нет.

- [ ] **Шаг 3: Компоненты `packages/ui`**

Добавить на токенах бренд-бука, каждый со своим тестом на доступность:

- `form-field.tsx` — подпись, поле, текст ошибки; связывает их через `htmlFor`/`aria-describedby`, ошибку помечает `role="alert"`. Без этого поле с ошибкой не читается вслух и не находится тестом.
- `password-input.tsx` — поле с кнопкой показа; кнопка имеет `aria-label` и `aria-pressed`.
- `dialog.tsx` — Radix Dialog с фокус-ловушкой (подтверждение отзыва сессии).
- `empty-state.tsx` — заголовок, описание, действие.
- `switch.tsx` — Radix Switch для переключателей.

Фокус во всех — видимый и акцентного цвета, как требует бренд-бук; это проверяется тестом токенов из подпроекта 0.

- [ ] **Шаг 4: Провайдер и гейт**

`auth-provider.tsx` — клиентский компонент: создаёт `TokenStore`, `AuthClient` и `QueryClient` один раз (`useState(() => …)`), кладёт в контекст `packages/core`. Базовый URL — относительный `''`: веб и API за одним nginx, и абсолютный адрес в сборке означал бы пересборку под каждое развёртывание.

`auth-guard.tsx`:

```tsx
'use client'

/**
 * Гейт кабинета.
 *
 * Проверка клиентская: refresh-cookie ограничена путём /api/auth/refresh, и
 * серверные компоненты Next её не видят — так и задумано, вся защита от CSRF
 * держится на том, что cookie доступна одному эндпоинту.
 */
export function AuthGuard({ children, router }: AuthGuardProps) {
  const { refresh } = useAuthClient()
  const [state, setState] = useState<'checking' | 'ready'>('checking')

  useEffect(() => {
    let cancelled = false
    void refresh().then((ok) => {
      if (cancelled) return
      if (ok) setState('ready')
      else router.replace('/login')
    })
    return () => {
      cancelled = true
    }
  }, [refresh, router])

  if (state === 'checking') return <AuthGuardSkeleton />
  return <>{children}</>
}
```

- [ ] **Шаг 5: Страница входа целиком**

Остальные страницы собираются по этому же образцу: схема из `packages/core`, мутация из хуков, ошибка через `role="alert"`, кнопка с состоянием ожидания.

`app/(auth)/login/page.tsx`:

```tsx
'use client'

import { detectLanguage, loginSchema, translate, useLogin } from '@repibot/core'
import { Button, FormField, PasswordInput } from '@repibot/ui'
import { useRouter } from 'next/navigation'
import { useMemo, useState } from 'react'

export default function LoginPage() {
  const router = useRouter()
  // Пользователь ещё неизвестен, язык профиля брать неоткуда — только из
  // настроек браузера.
  const language = useMemo(() => detectLanguage(navigator.languages ?? [navigator.language]), [])
  const t = (key: Parameters<typeof translate>[1]) => translate(language, key)
  const login = useLogin(language)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setFormError(null)

    // Проверка на клиенте — чтобы не гонять заведомо неверные данные; на
    // бэкенде те же правила проверяются заново, клиенту доверия нет.
    const parsed = loginSchema.safeParse({ email, password })
    if (!parsed.success) {
      setFormError(t('auth.error.form'))
      return
    }

    try {
      await login.mutateAsync(parsed.data)
      router.replace('/account')
    } catch (error) {
      setFormError(error instanceof Error ? error.message : t('auth.error.unknown'))
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto flex w-full max-w-sm flex-col gap-4">
      <h1 className="text-2xl font-semibold">{t('auth.login.title')}</h1>

      <FormField label={t('auth.field.email')} htmlFor="email">
        <input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </FormField>

      <FormField label={t('auth.field.password')} htmlFor="password">
        <PasswordInput
          id="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </FormField>

      {formError !== null && (
        <p role="alert" className="text-sm text-[var(--color-danger)]">
          {formError}
        </p>
      )}

      <Button type="submit" disabled={login.isPending}>
        {login.isPending ? t('auth.login.pending') : t('auth.login.submit')}
      </Button>

      <div className="flex justify-between text-sm">
        <a href="/register">{t('auth.login.register_link')}</a>
        <a href="/forgot-password">{t('auth.login.forgot_link')}</a>
      </div>

      {/* Кнопка появится в плане 1b вместе с OIDC. Показываем отключённой, чтобы
          вход через Telegram не выглядел отсутствующим в продукте. */}
      <Button type="button" variant="secondary" disabled>
        {t('auth.login.telegram_soon')}
      </Button>
    </form>
  )
}
```

Ключи `auth.error.form`, `auth.field.email`, `auth.field.password`, `auth.login.pending`, `auth.login.register_link`, `auth.login.forgot_link`, `auth.login.telegram_soon` добавляются в оба словаря вместе с остальными из задачи 18.

- [ ] **Шаг 6: Остальные страницы**

| Маршрут | Содержимое |
|---|---|
| `/login` | Форма почты и пароля, ссылки на регистрацию и восстановление, кнопка «Войти через Telegram» отключена с подписью «скоро» (появится в 1b) |
| `/register` | Форма регистрации; после успеха — экран «проверьте почту» с кнопкой повторной отправки |
| `/verify-email` | Читает `token` из строки запроса, отправляет запрос, при успехе уводит в кабинет, при ошибке предлагает повторить письмо |
| `/forgot-password` | Форма адреса; ответ всегда один и тот же — «письмо отправлено, если такой адрес есть» |
| `/reset-password` | Токен из строки запроса плюс новый пароль |
| `/account` | Имя, язык, реферальный код, адрес почты |
| `/account/security` | Смена пароля, список сессий с отзывом, состояние привязки Telegram (управление — в 1b) |
| `/confirm-email` | Подтверждение нового адреса по токену из письма. Публичный: письмо открывают там, где почта, а не там, где открыт кабинет |

Страницы кабинета помечаются `export const dynamic = 'force-dynamic'`: их содержимое зависит от текущего пользователя, и кэшировать разметку нельзя.

Раздел `/admin` из подпроекта 0 получает такой же гейт, но по роли: без `admin` или `support` — редирект на `/account`.

- [ ] **Шаг 7: Убедиться, что тесты проходят**

Run: `cd frontend && pnpm --filter @repibot/web test && pnpm --filter @repibot/ui test && pnpm -r exec tsc --noEmit && cd ..`
Expected: PASS.

- [ ] **Шаг 8: Коммит**

```bash
git add frontend/apps/web frontend/packages/ui
git commit -m "feat: экраны входа, регистрации и кабинета"
```

---

## Задача 20: MiniApp — автовход и профиль

**Файлы:**
- Изменить: `frontend/apps/miniapp/src/telegram.ts`, `src/router.tsx`, `src/routes/index.tsx`, `src/main.tsx`
- Создать: `frontend/apps/miniapp/src/auth.ts`, `src/routes/profile.tsx`
- Тест: `frontend/apps/miniapp/src/auth.test.ts`, `src/routes/profile.test.tsx`

**Интерфейсы:**
- Отдаёт: `exchangeInitData(client, initData) -> Promise<boolean>`; маршрут `/profile`; состояние входа в Zustand со значениями `'checking' | 'ready' | 'failed' | 'outside'`.

- [ ] **Шаг 1: Написать падающий тест**

```ts
describe('вход в MiniApp', () => {
  it('обменивает initData на токен', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ access_token: 'token', expires_in: 900 })),
    )
    const store = createTokenStore()

    const ok = await exchangeInitData({ baseUrl: '', store }, 'auth_date=1&hash=abc')

    expect(ok).toBe(true)
    expect(store.get()).toBe('token')
  })

  it('сообщает о неудаче, а не молчит', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({ error: { code: 'invalid_credentials' } }, { status: 401 }),
      ),
    )
    const store = createTokenStore()

    expect(await exchangeInitData({ baseUrl: '', store }, 'испорчено')).toBe(false)
    expect(store.get()).toBeNull()
  })

  it('различает открытие вне Telegram', async () => {
    // Без initData обмен не пробуется вовсе: сообщение «войдите через Telegram»
    // полезнее, чем сетевая ошибка.
    expect(await exchangeInitData({ baseUrl: '', store: createTokenStore() }, '')).toBe(false)
  })
})
```

Тест экрана профиля: показывает язык из `/api/me`, переключение отправляет `PATCH` и обновляет надпись; при неудачном входе экран показывает состояние с кнопкой «Повторить».

- [ ] **Шаг 2: Убедиться, что тесты падают**

Run: `cd frontend && pnpm --filter @repibot/miniapp test && cd ..`
Expected: FAIL.

- [ ] **Шаг 3: Реализовать вход**

`src/auth.ts`:

```ts
import type { TokenStore } from '@repibot/core'
import { create } from 'zustand'

import { readInitData } from './telegram'

export type AuthState = 'checking' | 'ready' | 'failed' | 'outside'

interface AuthOptions {
  baseUrl: string
  store: TokenStore
}

/**
 * Обмен initData на access-токен.
 *
 * Refresh здесь не используется: cookie в стороннем контексте веб-версии
 * Telegram не выживает. Вместо продления берётся свежий initData — Telegram
 * отдаёт его при каждом открытии, и он всегда моложе суток.
 */
export async function exchangeInitData(
  { baseUrl, store }: AuthOptions,
  initData: string,
): Promise<boolean> {
  // Пустая строка означает открытие вне Telegram. Сетевой запрос здесь дал бы
  // невнятную ошибку вместо понятного «откройте через бота».
  if (!initData) return false

  const response = await fetch(`${baseUrl}/api/auth/telegram/miniapp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ init_data: initData }),
  })

  if (!response.ok) {
    store.set(null)
    return false
  }

  const body = (await response.json()) as { access_token: string }
  store.set(body.access_token)
  return true
}

interface AuthStore {
  state: AuthState
  signIn: (options: AuthOptions) => Promise<void>
}

export const useAuthState = create<AuthStore>((set) => ({
  state: 'checking',
  async signIn(options) {
    const initData = readInitData()
    if (initData === null) {
      set({ state: 'outside' })
      return
    }
    set({ state: (await exchangeInitData(options, initData)) ? 'ready' : 'failed' })
  },
}))
```

- [ ] **Шаг 4: Экраны**

`routes/index.tsx` — четыре состояния из `useAuthState`: `checking` показывает скелет, `ready` — приветствие с именем из `useMe`, `failed` — сообщение с кнопкой повтора (`signIn` вызывается заново), `outside` — предложение открыть приложение через бота. Пустого экрана ни в одном состоянии быть не должно.

`routes/profile.tsx` — имя, переключатель языка на `Switch` из `packages/ui`, реферальный код; данные через `useMe`, сохранение через `useUpdateProfile`. После смены языка подписи перерисовываются сразу: язык берётся из ответа мутации, а не из локального состояния.

- [ ] **Шаг 5: Убедиться, что тесты проходят**

Run: `cd frontend && pnpm --filter @repibot/miniapp test && pnpm -r exec tsc --noEmit && cd ..`
Expected: PASS.

- [ ] **Шаг 6: Коммит**

```bash
git add frontend/apps/miniapp
git commit -m "feat: автовход и профиль в MiniApp"
```

---

## Задача 21: Сквозные тесты и документация

**Файлы:**
- Создать: `frontend/apps/web/e2e/auth.spec.ts`, `frontend/apps/web/e2e/mailpit.ts`
- Изменить: `frontend/apps/web/playwright.config.ts`, `README.md`, `CONTRIBUTING.md`, `docs/deployment.md`, `tools/check.py` (если нужен новый шаг)
- Тест: сами сценарии Playwright

**Интерфейсы:**
- Отдаёт: `waitForLink(mailpitUrl, recipient, pattern) -> Promise<string>` — читает последнее письмо получателя через API Mailpit и достаёт ссылку.

- [ ] **Шаг 1: Написать помощник чтения почты**

```ts
/**
 * Чтение письма из Mailpit.
 *
 * Сквозной тест обязан пройти тем же путём, что человек: получить письмо и
 * открыть ссылку. Достать токен из базы было бы проще и проверяло бы не то —
 * доставка писем ломается чаще, чем запись в таблицу.
 */
export async function waitForLink(
  mailpitUrl: string,
  recipient: string,
  pattern: RegExp,
  timeoutMs = 15_000,
): Promise<string> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const response = await fetch(`${mailpitUrl}/api/v1/search?query=to:${recipient}`)
    const body = (await response.json()) as { messages: { ID: string }[] }
    if (body.messages.length > 0) {
      const text = await fetch(`${mailpitUrl}/api/v1/message/${body.messages[0].ID}`)
        .then((message) => message.json() as Promise<{ Text: string }>)
        .then((message) => message.Text)
      const found = text.match(pattern)
      if (found) return found[0]
    }
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error(`письмо для ${recipient} не пришло за ${timeoutMs} мс`)
}
```

- [ ] **Шаг 2: Написать сценарии**

```ts
test('регистрация, подтверждение почты и вход', async ({ page }) => {
  const email = `user-${Date.now()}@example.test`

  await page.goto('/register')
  await page.getByLabel(/почта/i).fill(email)
  await page.getByLabel(/пароль/i).fill('совершенно обычный пароль')
  await page.getByRole('button', { name: /зарегистрироваться/i }).click()

  await expect(page.getByText(/проверьте почту/i)).toBeVisible()

  const link = await waitForLink(MAILPIT, email, /https?:\/\/\S+verify-email\S+/)
  await page.goto(link)

  await expect(page).toHaveURL(/\/account/)
  await expect(page.getByText(email)).toBeVisible()
})

test('кабинет закрыт без входа', async ({ page }) => {
  await page.goto('/account')

  await expect(page).toHaveURL(/\/login/)
})

test('сброс пароля пускает с новым паролем', async ({ page }) => {
  const email = `reset-${Date.now()}@example.test`
  await registerAndVerify(page, email, 'совершенно обычный пароль')

  await page.goto('/forgot-password')
  await page.getByLabel(/почта/i).fill(email)
  await page.getByRole('button', { name: /отправить/i }).click()
  await expect(page.getByText(/письмо отправлено/i)).toBeVisible()

  const link = await waitForLink(MAILPIT, email, /https?:\/\/\S+reset-password\S+/)
  await page.goto(link)
  await page.getByLabel(/новый пароль/i).fill('другой совершенно обычный пароль')
  await page.getByRole('button', { name: /сохранить/i }).click()

  await expect(page).toHaveURL(/\/account/)

  // Прежний пароль после сброса не работает — иначе сброс не защищает от угона.
  await page.goto('/account')
  await page.getByRole('button', { name: /выйти/i }).click()
  await page.goto('/login')
  await page.getByLabel(/почта/i).fill(email)
  await page.getByLabel(/пароль/i).fill('совершенно обычный пароль')
  await page.getByRole('button', { name: /войти/i }).click()
  await expect(page.getByRole('alert')).toBeVisible()
})

test('отзыв сессии обрывает доступ', async ({ page, browser }) => {
  const email = `revoke-${Date.now()}@example.test`
  const password = 'совершенно обычный пароль'
  await registerAndVerify(page, email, password)

  // Второй контекст — это второе устройство: своя cookie, своя сессия.
  const second = await browser.newContext()
  const secondPage = await second.newPage()
  await secondPage.goto('/login')
  await secondPage.getByLabel(/почта/i).fill(email)
  await secondPage.getByLabel(/пароль/i).fill(password)
  await secondPage.getByRole('button', { name: /войти/i }).click()
  await expect(secondPage).toHaveURL(/\/account/)

  await page.goto('/account/security')
  await page.getByRole('button', { name: /отозвать/i }).first().click()
  await page.getByRole('button', { name: /подтвердить/i }).click()

  await secondPage.goto('/account')
  await expect(secondPage).toHaveURL(/\/login/)

  await second.close()
})
```

Вспомогательная функция, которую используют оба сценария:

```ts
async function registerAndVerify(page: Page, email: string, password: string): Promise<void> {
  await page.goto('/register')
  await page.getByLabel(/почта/i).fill(email)
  await page.getByLabel(/пароль/i).fill(password)
  await page.getByRole('button', { name: /зарегистрироваться/i }).click()

  const link = await waitForLink(MAILPIT, email, /https?:\/\/\S+verify-email\S+/)
  await page.goto(link)
  await expect(page).toHaveURL(/\/account/)
}
```

Первый сценарий переписывается на неё же, чтобы шаги регистрации не были продублированы трижды.

- [ ] **Шаг 3: Настроить окружение тестов**

В `playwright.config.ts` добавить `webServer`, поднимающий стек командой `docker compose --profile dev up -d --wait`, и переменную `MAILPIT=http://localhost:8025`. Стек поднимается с `EMAIL_SENDER=smtp`, `SMTP_HOST=mailpit`, `SMTP_PORT=1025` — иначе письма не дойдут до Mailpit.

- [ ] **Шаг 4: Прогнать сценарии**

Run: `cd frontend && pnpm --filter @repibot/web exec playwright test && cd ..`
Expected: четыре сценария зелёные.

- [ ] **Шаг 5: Обновить документацию**

- `README.md`: текущее состояние — «подпроект 1a: вход и профиль»; в таблице каталогов добавить `backend/core/services/auth`; в разделе разработки — как локально получить письмо (Mailpit под профилем `dev` или `EMAIL_SENDER=log` и ссылка в журнале).
- `CONTRIBUTING.md`: раздел про то, что бизнес-логика входа живёт в `services/auth`, а роутеры и хендлеры её не содержат; про запрет писать секреты и токены в журнал.
- `docs/deployment.md`: `ADMIN_TELEGRAM_IDS`, переменные SMTP, предупреждение про необратимость переключения на OpenID Connect в BotFather и про регистрацию redirect URI (понадобится в 1b, но настраивается один раз при установке).

- [ ] **Шаг 6: Полная проверка и коммит**

Run: `uv run check`
Expected: все проверки зелёные.

```bash
git add frontend/apps/web README.md CONTRIBUTING.md docs/deployment.md
git commit -m "test: сквозные сценарии входа и обновление документации"
```

---

## Критерии готовности этапа 1a

Проверяется руками на поднятом стеке, а не только тестами:

1. Регистрация по почте создаёт аккаунт; вход до подтверждения отвечает `email_not_verified`.
2. Письмо видно в Mailpit, ссылка подтверждает адрес и пускает в кабинет.
3. Остановленный `mailpit` не ломает регистрацию: после запуска письмо приходит само.
4. Две открытые вкладки кабинета работают одновременно и не разлогинивают друг друга.
5. MiniApp в Telegram открывается и входит без пароля; профиль показывает язык.
6. Смена языка в профиле меняет язык писем и ответов бота.
7. Пользователь из `ADMIN_TELEGRAM_IDS` проходит `/api/admin/whoami`, обычный получает `403`, запись о повышении есть в `audit_log`.
8. Отзыв сессии в `/account/security` немедленно закрывает доступ этой сессии.
9. Шесть неудачных попыток входа подряд дают `429` с `Retry-After`.
10. `uv run check` проходит целиком.

## Что переходит в план 1b

Passkey, Telegram OIDC в браузере, привязка Telegram по коду через бота с поглощением пустого дубля, отвязка способов входа по правилу `can_unlink`, таблица `passkey_credentials` и поле `passkey_count` в профиле, кнопка «Войти через Telegram» на `/login`.
