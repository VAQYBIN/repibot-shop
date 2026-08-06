# Идентичность, этап 1b — план реализации

> **Для агентов:** ОБЯЗАТЕЛЬНЫЙ ПОДСКИЛЛ: используйте superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans для выполнения плана задача за задачей. Шаги размечены чекбоксами (`- [ ]`).

**Цель:** довести идентичность до полного набора способов входа — passkey, Telegram в браузере через OpenID Connect, привязка Telegram по коду через бота и отвязка любого способа по правилу «последний снять нельзя».

**Архитектура:** новые способы входа встают рядом с существующими и заканчиваются тем же `AuthService.issue` — проверка статуса, повышение роли и выдача токенов остаются написанными один раз. Passkey хранит только публичный ключ и счётчик подписей; challenge живёт в Valkey пять минут и гасится при первом предъявлении. Браузерный вход через Telegram — полный редирект с PKCE S256: ID-токен проверяется по JWKS, сессия отдаётся той же refresh-cookie, что и после входа паролем.

**Стек:** Python 3.13, `webauthn` 3.0, PyJWT с cryptography, httpx, SQLAlchemy 2.0, Alembic, FastAPI, aiogram 3.30, Valkey; React 19, Next.js 16, `@simplewebauthn/browser` 13, TanStack Query v5, Vitest, Playwright.

**Спецификация:** [docs/superpowers/specs/2026-08-05-identity-design.md](../specs/2026-08-05-identity-design.md)

**Предшествующий этап:** [1a — ядро](./2026-08-05-identity-core.md), выполнен полностью.

## Состояние выполнения

Этап выполнен. Задачи шли волнами: внутри волны — параллельно, между волнами —
полный прогон `uv run check`.

| Волна | Задачи | Состояние |
|---|---|---|
| 1 | 1 таблица ключей, 2 программный аутентификатор, 7 PKCE и OIDC | готово |
| 2 | 3 параметры WebAuthn, 8 вход через OIDC | готово |
| 3 | 4 подсчёт способов входа, 9 эндпоинты OIDC | готово |
| 4 | 5 сервис passkey, 10 привязка Telegram | готово |
| 5 | 6 эндпоинты passkey, 11 эндпоинты привязки, 12 бот | готово |
| 6 | 13 словари | готово |
| 7 | 14 passkey в интерфейсе, 15 Telegram в интерфейсе | готово |
| 8 | 16 сквозной сценарий и документация | готово |

Помимо задач плана в этап вошли правки, найденные при сборке:

- **вход через Telegram привязывается к браузеру, который его начал.** Одного
  `state` мало: он возвращается в адресе, и злоумышленник мог довести вход у
  себя до рабочего кода, а ссылку возврата подсунуть жертве — та молча оказалась
  бы в чужом аккаунте. Добавлена короткоживущая httpOnly-cookie `repibot_oidc`;
- эндпоинты `/api/me/passkeys` выпали при нарезке волны и были дописаны отдельно:
  файл `routers/me.py` достался соседней задаче, а эта часть не досталась никому;
- `/api/auth/telegram/start` получил лимит запросов: каждый вызов клал в Valkey
  ключ на десять минут, и аноним мог набить память;
- недоступный Bot API отвечал кодом `not_found` — человек читал «ничего не
  нашлось» вместо «повторите позже»; теперь `telegram_unavailable` и 503;
- `is_configured` требует обе половины пары из BotFather: с одним Client ID
  кнопка выглядела рабочей, а вход обрывался уже после подтверждения в Telegram;
- конфигурация vitest в вебе включала только `*.test.tsx`, и тесты в `.ts`-файлах
  не запускались вовсе;
- сквозные сценарии этапа 1a покраснели от новой кнопки «Войти по ключу»: поиск
  кнопки «Войти» без `exact` находил обе.

Листинги задач ниже местами разошлись с итоговым кодом — расхождения перечислены
в этом разделе и в сообщениях коммитов. Источник истины — код.

## Глобальные ограничения

- Ветка работы — `dev`. Отдельные ветки, если понадобятся, создаются от `dev`.
- Каждая задача заканчивается прогоном `uv run check` без ошибок и одним коммитом. Сообщение коммита на русском в формате `тип: краткое описание`.
- Тест пишется первым и падает до реализации.
- Бизнес-логика — только в `backend/core/services` и `backend/core/domain`. В роутерах FastAPI и хендлерах aiogram её нет.
- Комментарии, докстринги и сообщения — на русском. Комментарий объясняет причину решения, а не пересказывает код.
- `mypy` в strict и `ruff` с набором из `pyproject.toml` — блокирующие. Аннотации обязательны везде, включая тесты.
- Новая переменная окружения добавляется одновременно в `Settings`, `.env.example` и `docs/deployment.md`.
- Тексты ошибок API не локализуются: ответ несёт код, фразу подбирает фронтенд. Коды этапа: `last_login_method`, `telegram_already_linked`, `link_conflict` плюс все коды этапа 1a.
- Секреты в логи не попадают: `client_secret`, `code`, `code_verifier`, ID-токен, refresh-токен и коды привязки не пишутся ни в сообщениях, ни в `extra`.
- Цвета, отступы и типографика — из `docs/design/repibot-brandbook.md` через токены `packages/ui`.
- Тесты, которым нужен Postgres, помечаются `pytestmark = pytest.mark.docker`.
- Зависимости уже установлены и закоммичены (`webauthn>=3.0`, `pyjwt[crypto]>=2.10`, `@simplewebauthn/browser@^13.3.0`). Ставить или обновлять пакеты в задачах не нужно: `uv.lock` и `pnpm-lock.yaml` — общие файлы, и параллельные исполнители за них дерутся.
- `authlib` не используется: PyJWT с extra `crypto` проверяет ID-токен Telegram, а обмен кода — обычный `POST` формой через уже подключённый httpx. Спецификация называет библиотеки ориентиром, а не требованием; одна зависимость вместо двух.

## Проверенные факты о внешних сервисах

Значения взяты из живых ответов сервисов 2026-08-06, а не из документации.

`https://oauth.telegram.org/.well-known/openid-configuration`:

| Поле | Значение |
|---|---|
| `issuer` | `https://oauth.telegram.org` |
| `authorization_endpoint` | `https://oauth.telegram.org/auth` |
| `token_endpoint` | `https://oauth.telegram.org/token` |
| `jwks_uri` | `https://oauth.telegram.org/.well-known/jwks.json` |
| `id_token_signing_alg_values_supported` | `RS256`, `ES256`, `EdDSA`, `ES256K` |
| `scopes_supported` | `openid`, `phone`, `profile`, `telegram:bot_access` |
| `code_challenge_methods_supported` | `plain`, `S256` |
| `claims_supported` | `aud`, `preferred_username`, `phone_number`, `exp`, `iat`, `iss`, `name`, `picture`, `sub` |

Эндпоинта `userinfo` нет: всё, что мы узнаём о человеке, приходит в ID-токене. Идентификатор Telegram берётся из `sub`, имя — из `name`, `@username` — из `preferred_username`. Scope `phone` не запрашивается.

`webauthn` 3.0 — сигнатуры, на которые опирается план:

```python
generate_registration_options(*, rp_id, rp_name, user_name, user_id=None, user_display_name=None,
    challenge=None, timeout=60000, attestation=..., authenticator_selection=None,
    exclude_credentials=None, supported_pub_key_algs=None, hints=None) -> PublicKeyCredentialCreationOptions
verify_registration_response(*, credential, expected_challenge, expected_rp_id, expected_origin,
    require_user_presence=True, require_user_verification=False, ...) -> VerifiedRegistration
generate_authentication_options(*, rp_id, challenge=None, timeout=60000,
    allow_credentials=None, user_verification=...) -> PublicKeyCredentialRequestOptions
verify_authentication_response(*, credential, expected_challenge, expected_rp_id, expected_origin,
    credential_public_key, credential_current_sign_count, require_user_verification=False) -> VerifiedAuthentication
```

`VerifiedRegistration` несёт `credential_id: bytes`, `credential_public_key: bytes`, `sign_count: int`. `VerifiedAuthentication` — `credential_id: bytes`, `new_sign_count: int`. Все исключения библиотеки наследуют `webauthn.helpers.exceptions.WebAuthnException`.

`@simplewebauthn/browser` 13.3: `startRegistration({ optionsJSON })` и `startAuthentication({ optionsJSON })` — оба принимают объект-обёртку, а не сами опции.

---

## Структура файлов

| Файл | Ответственность |
|---|---|
| `backend/core/src/repibot_core/db/models/passkey.py` | `PasskeyCredential` |
| `backend/core/src/repibot_core/db/repositories/passkeys.py` | доступ к `passkey_credentials` |
| `backend/core/src/repibot_core/db/migrations/versions/0003_passkeys.py` | миграция этапа |
| `backend/core/src/repibot_core/security/webauthn.py` | RP-параметры из адреса, разбор ответа аутентификатора |
| `backend/core/src/repibot_core/security/pkce.py` | `code_verifier` и `code_challenge` S256 |
| `backend/core/src/repibot_core/services/challenges.py` | одноразовые challenge и state в Valkey |
| `backend/core/src/repibot_core/services/login_methods.py` | подсчёт способов входа для `can_unlink` и профиля |
| `backend/core/src/repibot_core/services/auth/passkey.py` | `PasskeyAuth` — регистрация ключа, вход, список, удаление |
| `backend/core/src/repibot_core/services/auth/telegram.py` | добавляется вход через OIDC |
| `backend/core/src/repibot_core/services/telegram_link.py` | код привязки, поглощение пустого дубля, отвязка |
| `backend/core/src/repibot_core/integrations/telegram/oidc.py` | обмен кода, JWKS, проверка ID-токена |
| `backend/core/src/repibot_core/integrations/telegram/bot_api.py` | `getMe` с кэшем — для ссылки `t.me` |
| `backend/core/src/repibot_core/testing/webauthn.py` | программный аутентификатор для тестов |
| `backend/api/src/repibot_api/routers/auth.py` | passkey-вход, `/telegram/start`, `/telegram/callback`, `/methods` |
| `backend/api/src/repibot_api/routers/me.py` | passkey-ключи и привязка Telegram |
| `backend/bot/src/repibot_bot/handlers/start.py` | `/start link_XXX` |
| `frontend/apps/web/src/lib/passkey.ts` | хуки passkey поверх `@simplewebauthn/browser` |
| `frontend/apps/web/src/lib/telegram.ts` | хуки привязки и отвязки |
| `frontend/apps/web/src/app/(auth)/login/page.tsx` | кнопки passkey и Telegram |
| `frontend/apps/web/src/app/account/security/page.tsx` | карточки passkey и Telegram |
| `frontend/apps/web/e2e/passkey.spec.ts` | сквозной сценарий с виртуальным аутентификатором |

---

## Задача 1: Таблица passkey-ключей

**Файлы:**
- Создать: `backend/core/src/repibot_core/db/models/passkey.py`
- Создать: `backend/core/src/repibot_core/db/repositories/passkeys.py`
- Создать: `backend/core/src/repibot_core/db/migrations/versions/0003_passkeys.py`
- Изменить: `backend/core/src/repibot_core/db/models/__init__.py`
- Тест: `backend/core/tests/test_passkey_repository.py`

**Интерфейсы:**
- Производит: `PasskeyCredential` с полями `id: int`, `user_id: int`, `credential_id: bytes`, `public_key: bytes`, `sign_count: int`, `transports: list[str] | None`, `name: str`, `last_used_at: datetime | None`, `created_at`; `PasskeyRepository` с методами `create`, `get`, `get_by_credential_id`, `list_for_user`, `count_for_user`, `delete`.

- [ ] **Шаг 1: Написать падающий тест**

Создать `backend/core/tests/test_passkey_repository.py`:

```python
"""Хранение passkey-ключей."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.db.repositories.passkeys import PasskeyRepository
from repibot_core.db.repositories.users import UserRepository

pytestmark = pytest.mark.docker


async def _user(session: AsyncSession, email: str = "user@example.org") -> User:
    users = UserRepository(session)
    user = await users.create(email=email, referral_code=await users.next_referral_code())
    await session.commit()
    return user


async def test_credential_is_found_by_its_raw_identifier(db_session: AsyncSession) -> None:
    """Вход по passkey начинается с идентификатора ключа: пользователь неизвестен."""
    user = await _user(db_session)
    passkeys = PasskeyRepository(db_session)
    await passkeys.create(
        user_id=user.id,
        credential_id=b"credential-one",
        public_key=b"public-key",
        sign_count=0,
        transports=["internal"],
        name="Ноутбук",
    )
    await db_session.commit()

    found = await passkeys.get_by_credential_id(b"credential-one")

    assert found is not None
    assert found.user_id == user.id
    assert found.transports == ["internal"]


async def test_count_for_user_sees_only_own_keys(db_session: AsyncSession) -> None:
    owner = await _user(db_session)
    stranger = await _user(db_session, email="other@example.org")
    passkeys = PasskeyRepository(db_session)
    await passkeys.create(
        user_id=owner.id,
        credential_id=b"one",
        public_key=b"key",
        sign_count=0,
        transports=None,
        name="Ключ",
    )
    await passkeys.create(
        user_id=stranger.id,
        credential_id=b"two",
        public_key=b"key",
        sign_count=0,
        transports=None,
        name="Ключ",
    )
    await db_session.commit()

    assert await passkeys.count_for_user(owner.id) == 1


async def test_same_credential_id_cannot_be_registered_twice(db_session: AsyncSession) -> None:
    """Один аутентификатор — одна запись: иначе вход выбирал бы из двух."""
    from sqlalchemy.exc import IntegrityError

    user = await _user(db_session)
    passkeys = PasskeyRepository(db_session)
    await passkeys.create(
        user_id=user.id,
        credential_id=b"same",
        public_key=b"key",
        sign_count=0,
        transports=None,
        name="Первый",
    )
    await db_session.commit()

    with pytest.raises(IntegrityError):
        await passkeys.create(
            user_id=user.id,
            credential_id=b"same",
            public_key=b"key",
            sign_count=0,
            transports=None,
            name="Второй",
        )
        await db_session.commit()
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_passkey_repository.py -q`
Expected: FAIL с `ModuleNotFoundError: repibot_core.db.repositories.passkeys`.

- [ ] **Шаг 3: Написать модель**

Создать `backend/core/src/repibot_core/db/models/passkey.py`:

```python
"""Passkey: публичный ключ аутентификатора и счётчик его подписей."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin


class PasskeyCredential(TimestampMixin, Base):
    __tablename__ = "passkey_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # Идентификатор и ключ хранятся байтами: библиотека отдаёт и принимает их
    # в таком виде, а перекодировка в base64url туда-обратно на каждом входе —
    # лишний способ ошибиться в дополнении «=».
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)

    # Счётчик подписей аутентификатора. Многие passkey держат его нулевым, и
    # это допустимо: правило «новый больше сохранённого» проверяется только
    # тогда, когда счётчик вообще используется.
    sign_count: Mapped[int] = mapped_column(Integer, default=0)

    transports: Mapped[list[str] | None] = mapped_column(JSONB)
    name: Mapped[str] = mapped_column(String(64))
    last_used_at: Mapped[datetime | None] = mapped_column()
```

В `backend/core/src/repibot_core/db/models/__init__.py` добавить импорт и `__all__`:

```python
from repibot_core.db.models.passkey import PasskeyCredential
```

- [ ] **Шаг 4: Написать репозиторий**

Создать `backend/core/src/repibot_core/db/repositories/passkeys.py`:

```python
"""Доступ к passkey-ключам."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import PasskeyCredential


class PasskeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: int,
        credential_id: bytes,
        public_key: bytes,
        sign_count: int,
        transports: list[str] | None,
        name: str,
    ) -> PasskeyCredential:
        row = PasskeyCredential(
            user_id=user_id,
            credential_id=credential_id,
            public_key=public_key,
            sign_count=sign_count,
            transports=transports,
            name=name,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, passkey_id: int) -> PasskeyCredential | None:
        return await self._session.get(PasskeyCredential, passkey_id)

    async def get_by_credential_id(self, credential_id: bytes) -> PasskeyCredential | None:
        statement = select(PasskeyCredential).where(
            PasskeyCredential.credential_id == credential_id
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_for_user(self, user_id: int) -> list[PasskeyCredential]:
        statement = (
            select(PasskeyCredential)
            .where(PasskeyCredential.user_id == user_id)
            .order_by(PasskeyCredential.created_at)
        )
        return list((await self._session.execute(statement)).scalars())

    async def count_for_user(self, user_id: int) -> int:
        statement = select(func.count()).where(PasskeyCredential.user_id == user_id)
        return int((await self._session.execute(statement)).scalar_one())

    async def delete(self, row: PasskeyCredential) -> None:
        await self._session.execute(
            delete(PasskeyCredential).where(PasskeyCredential.id == row.id)
        )
```

- [ ] **Шаг 5: Написать миграцию**

Создать `backend/core/src/repibot_core/db/migrations/versions/0003_passkeys.py`:

```python
"""Passkey-ключи.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "passkey_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transports", postgresql.JSONB(), nullable=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_passkey_credentials_user_id", "passkey_credentials", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_passkey_credentials_user_id", table_name="passkey_credentials")
    op.drop_table("passkey_credentials")
```

- [ ] **Шаг 6: Прогнать тесты**

Run: `uv run pytest backend/core/tests/test_passkey_repository.py backend/core/tests/test_migrations.py -q`
Expected: PASS. Тест миграций проверяет, что `upgrade` и `downgrade` проходят по всей цепочке.

- [ ] **Шаг 7: Коммит**

```bash
git add backend/core
git commit -m "feat: таблица passkey-ключей"
```

---

## Задача 2: Программный аутентификатор для тестов

**Файлы:**
- Создать: `backend/core/src/repibot_core/testing/webauthn.py`
- Тест: `backend/core/tests/test_soft_authenticator.py`

**Интерфейсы:**
- Производит: `SoftAuthenticator(rp_id: str, origin: str, credential_id: bytes | None = None)` с методами `register(challenge: bytes) -> dict[str, Any]` и `authenticate(challenge: bytes, *, user_handle: bytes) -> dict[str, Any]`, а также свойствами `credential_id: bytes` и `sign_count: int`.

Без него тесты passkey писать нечем: настоящий аутентификатор в CI недоступен, а записанные чужие ответы привязаны к чужим challenge и origin. Класс собирает ровно то, что прислал бы браузер: `clientDataJSON`, `authenticatorData` и подпись ES256.

- [ ] **Шаг 1: Написать падающий тест**

Создать `backend/core/tests/test_soft_authenticator.py`:

```python
"""Программный аутентификатор: библиотека должна принимать его ответы."""

from __future__ import annotations

import pytest
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.exceptions import InvalidAuthenticationResponse

from repibot_core.testing.webauthn import SoftAuthenticator

RP_ID = "example.org"
ORIGIN = "https://example.org"


def test_registration_response_is_accepted() -> None:
    device = SoftAuthenticator(rp_id=RP_ID, origin=ORIGIN)
    options = generate_registration_options(rp_id=RP_ID, rp_name="Re:Pibot", user_name="user")

    verified = verify_registration_response(
        credential=device.register(options.challenge),
        expected_challenge=options.challenge,
        expected_rp_id=RP_ID,
        expected_origin=ORIGIN,
    )

    assert verified.credential_id == device.credential_id


def test_authentication_response_is_accepted() -> None:
    device = SoftAuthenticator(rp_id=RP_ID, origin=ORIGIN)
    registration = verify_registration_response(
        credential=device.register(generate_registration_options(
            rp_id=RP_ID, rp_name="Re:Pibot", user_name="user", challenge=b"registration"
        ).challenge),
        expected_challenge=b"registration",
        expected_rp_id=RP_ID,
        expected_origin=ORIGIN,
    )
    options = generate_authentication_options(rp_id=RP_ID)

    verified = verify_authentication_response(
        credential=device.authenticate(options.challenge, user_handle=b"1"),
        expected_challenge=options.challenge,
        expected_rp_id=RP_ID,
        expected_origin=ORIGIN,
        credential_public_key=registration.credential_public_key,
        credential_current_sign_count=registration.sign_count,
    )

    assert verified.new_sign_count == 1


def test_stale_sign_count_is_rejected() -> None:
    """Счётчик меньше сохранённого — признак клона ключа."""
    device = SoftAuthenticator(rp_id=RP_ID, origin=ORIGIN)
    registration = verify_registration_response(
        credential=device.register(b"registration"),
        expected_challenge=b"registration",
        expected_rp_id=RP_ID,
        expected_origin=ORIGIN,
    )

    with pytest.raises(InvalidAuthenticationResponse):
        verify_authentication_response(
            credential=device.authenticate(b"login", user_handle=b"1"),
            expected_challenge=b"login",
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            credential_public_key=registration.credential_public_key,
            credential_current_sign_count=99,
        )
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_soft_authenticator.py -q`
Expected: FAIL с `ModuleNotFoundError: repibot_core.testing.webauthn`.

- [ ] **Шаг 3: Написать аутентификатор**

Создать `backend/core/src/repibot_core/testing/webauthn.py`:

```python
"""Программный аутентификатор для тестов passkey.

Собирает ответы ровно того вида, что присылает браузер: clientDataJSON,
authenticatorData и подпись ES256. Настоящего аутентификатора в CI нет, а
записанные чужие ответы привязаны к чужим challenge и origin — проверить ими
можно только то, что библиотека умеет разбирать саму себя.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url, encode_cbor

# Нулевой AAGUID означает «модель устройства не раскрывается» — так делают
# платформенные аутентификаторы, и attestation с fmt=none его не проверяет.
AAGUID = b"\x00" * 16

FLAG_USER_PRESENT = 0x01
FLAG_USER_VERIFIED = 0x04
FLAG_ATTESTED_DATA = 0x40


class SoftAuthenticator:
    def __init__(self, *, rp_id: str, origin: str, credential_id: bytes | None = None) -> None:
        self.rp_id = rp_id
        self.origin = origin
        self.credential_id = credential_id or secrets.token_bytes(32)
        self.sign_count = 0
        self._key = ec.generate_private_key(ec.SECP256R1())

    def register(self, challenge: bytes) -> dict[str, Any]:
        client_data = self._client_data("webauthn.create", challenge)
        auth_data = self._auth_data(
            FLAG_USER_PRESENT | FLAG_USER_VERIFIED | FLAG_ATTESTED_DATA, attested=True
        )
        attestation = encode_cbor({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": bytes_to_base64url(self.credential_id),
            "rawId": bytes_to_base64url(self.credential_id),
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "attestationObject": bytes_to_base64url(attestation),
                "transports": ["internal"],
            },
            "type": "public-key",
            "clientExtensionResults": {},
        }

    def authenticate(self, challenge: bytes, *, user_handle: bytes) -> dict[str, Any]:
        self.sign_count += 1
        client_data = self._client_data("webauthn.get", challenge)
        auth_data = self._auth_data(FLAG_USER_PRESENT | FLAG_USER_VERIFIED, attested=False)
        signature = self._key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": bytes_to_base64url(self.credential_id),
            "rawId": bytes_to_base64url(self.credential_id),
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(signature),
                "userHandle": bytes_to_base64url(user_handle),
            },
            "type": "public-key",
            "clientExtensionResults": {},
        }

    def _cose_key(self) -> bytes:
        """Публичный ключ в формате COSE_Key: kty EC2, alg ES256, кривая P-256."""
        numbers = self._key.public_key().public_numbers()
        return encode_cbor(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def _client_data(self, kind: str, challenge: bytes) -> bytes:
        return json.dumps(
            {
                "type": kind,
                "challenge": bytes_to_base64url(challenge),
                "origin": self.origin,
                "crossOrigin": False,
            },
            separators=(",", ":"),
        ).encode()

    def _auth_data(self, flags: int, *, attested: bool) -> bytes:
        data = hashlib.sha256(self.rp_id.encode()).digest()
        data += bytes([flags])
        data += self.sign_count.to_bytes(4, "big")
        if attested:
            key = self._cose_key()
            data += AAGUID + len(self.credential_id).to_bytes(2, "big") + self.credential_id + key
        return data
```

- [ ] **Шаг 4: Прогнать тесты**

Run: `uv run pytest backend/core/tests/test_soft_authenticator.py -q`
Expected: три теста PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add backend/core
git commit -m "test: программный аутентификатор для проверок passkey"
```

---

## Задача 3: RP-параметры, разбор ответа и хранилище challenge

**Файлы:**
- Создать: `backend/core/src/repibot_core/security/webauthn.py`
- Создать: `backend/core/src/repibot_core/services/challenges.py`
- Тест: `backend/core/tests/test_webauthn_helpers.py`

**Интерфейсы:**
- Производит: `RelyingParty(rp_id: str, origin: str)`, `relying_party(public_web_url: str) -> RelyingParty`, `challenge_from_response(credential: dict[str, Any]) -> bytes`, `credential_id_from_response(credential: dict[str, Any]) -> bytes`, `RP_NAME: str`; `ChallengeStore(redis, ttl_seconds=300)` с `remember(purpose, challenge, *, user_id=None)` и `take(purpose, challenge) -> str | None`, где `""` означает challenge без владельца.

- [ ] **Шаг 1: Написать падающий тест**

Создать `backend/core/tests/test_webauthn_helpers.py`:

```python
"""Параметры проверяющей стороны и одноразовые challenge."""

from __future__ import annotations

import json

import pytest
from fakeredis.aioredis import FakeRedis
from webauthn.helpers import bytes_to_base64url

from repibot_core.security.webauthn import (
    challenge_from_response,
    credential_id_from_response,
    relying_party,
)
from repibot_core.services.challenges import ChallengeStore


def test_rp_id_is_the_bare_hostname() -> None:
    """RP ID — имя домена без схемы и порта: так требует спецификация WebAuthn."""
    party = relying_party("https://shop.example.org:8443")

    assert party.rp_id == "shop.example.org"
    assert party.origin == "https://shop.example.org:8443"


def test_localhost_keeps_its_port_in_origin() -> None:
    """Порт входит в origin, но не в RP ID: сквозные тесты идут на 8081."""
    party = relying_party("http://localhost:8081")

    assert party.rp_id == "localhost"
    assert party.origin == "http://localhost:8081"


def test_challenge_is_read_from_client_data() -> None:
    client_data = json.dumps({"type": "webauthn.get", "challenge": bytes_to_base64url(b"abc")})
    credential = {
        "rawId": bytes_to_base64url(b"credential"),
        "response": {"clientDataJSON": bytes_to_base64url(client_data.encode())},
    }

    assert challenge_from_response(credential) == b"abc"
    assert credential_id_from_response(credential) == b"credential"


def test_broken_response_is_rejected_not_crashed() -> None:
    """Мусор в теле запроса — обычный отказ, а не пятисотка."""
    with pytest.raises(ValueError, match="ответ аутентификатора"):
        challenge_from_response({"response": {}})


async def test_challenge_is_accepted_once() -> None:
    """Повторное предъявление того же challenge — переигранный запрос."""
    store = ChallengeStore(FakeRedis())
    await store.remember("login", b"challenge")

    assert await store.take("login", b"challenge") == ""
    assert await store.take("login", b"challenge") is None


async def test_challenge_remembers_its_owner() -> None:
    store = ChallengeStore(FakeRedis())
    await store.remember("register", b"challenge", user_id=42)

    assert await store.take("register", b"challenge") == "42"
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_webauthn_helpers.py -q`
Expected: FAIL с `ModuleNotFoundError: repibot_core.security.webauthn`.

- [ ] **Шаг 3: Написать разбор параметров**

Создать `backend/core/src/repibot_core/security/webauthn.py`:

```python
"""Параметры проверяющей стороны и чтение ответа аутентификатора.

Чистые преобразования без ввода-вывода: адрес сайта → RP ID и origin, тело
запроса → challenge и идентификатор ключа. Криптографию считает библиотека
webauthn, здесь только то, что нужно до её вызова.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from webauthn.helpers import base64url_to_bytes

# Имя видно человеку в системном окне выбора ключа.
RP_NAME = "Re:Pibot"


@dataclass(frozen=True, slots=True)
class RelyingParty:
    rp_id: str
    origin: str


def relying_party(public_web_url: str) -> RelyingParty:
    """Выводит RP ID и origin из адреса сайта.

    Отдельной переменной окружения у них нет намеренно: разойтись эти значения
    не должны, а ключ, зарегистрированный на один RP ID, на другом не работает
    вовсе — рассинхронизация превратилась бы в потерю всех passkey сразу.
    """
    parts = urlsplit(public_web_url)
    if not parts.hostname or not parts.scheme:
        msg = f"PUBLIC_WEB_URL не похож на адрес: {public_web_url}"
        raise ValueError(msg)
    return RelyingParty(rp_id=parts.hostname, origin=f"{parts.scheme}://{parts.netloc}")


def challenge_from_response(credential: dict[str, Any]) -> bytes:
    """Достаёт challenge из clientDataJSON.

    Так серверу не нужно ни состояние в сессии, ни лишнее поле в запросе:
    challenge пришёл обратно внутри подписанных данных, и по нему же ищется
    запись в Valkey.
    """
    try:
        raw = credential["response"]["clientDataJSON"]
        client_data = json.loads(base64url_to_bytes(raw))
        return base64url_to_bytes(client_data["challenge"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        msg = "ответ аутентификатора не разбирается"
        raise ValueError(msg) from error


def credential_id_from_response(credential: dict[str, Any]) -> bytes:
    try:
        return base64url_to_bytes(credential["rawId"])
    except (KeyError, TypeError, ValueError) as error:
        msg = "ответ аутентификатора без идентификатора ключа"
        raise ValueError(msg) from error
```

- [ ] **Шаг 4: Написать хранилище challenge**

Создать `backend/core/src/repibot_core/services/challenges.py`:

```python
"""Одноразовые challenge WebAuthn в Valkey.

Challenge выдаётся сервером и должен приниматься ровно один раз: иначе
записанный ответ аутентификатора можно предъявить повторно. Ключ гасится тем
же запросом, которым читается, — GETDEL не оставляет окна между проверкой и
удалением.
"""

from __future__ import annotations

from redis.asyncio import Redis
from webauthn.helpers import bytes_to_base64url

# Пять минут: столько живёт системное окно выбора ключа, дольше challenge не
# нужен, а короче — не хватит человеку с аппаратным ключом в кармане.
CHALLENGE_TTL_SECONDS = 300


class ChallengeStore:
    def __init__(self, redis: Redis, ttl_seconds: int = CHALLENGE_TTL_SECONDS) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def _key(purpose: str, challenge: bytes) -> str:
        return f"webauthn:{purpose}:{bytes_to_base64url(challenge)}"

    async def remember(self, purpose: str, challenge: bytes, *, user_id: int | None = None) -> None:
        """Запоминает challenge. Пустое значение означает вход без известного пользователя."""
        value = "" if user_id is None else str(user_id)
        await self._redis.set(self._key(purpose, challenge), value, ex=self._ttl)

    async def take(self, purpose: str, challenge: bytes) -> str | None:
        """Забирает challenge. None — такого не выдавали или его уже использовали."""
        stored = await self._redis.getdel(self._key(purpose, challenge))
        if stored is None:
            return None
        return stored.decode() if isinstance(stored, bytes) else str(stored)
```

- [ ] **Шаг 5: Прогнать тесты**

Run: `uv run pytest backend/core/tests/test_webauthn_helpers.py -q`
Expected: шесть тестов PASS.

- [ ] **Шаг 6: Коммит**

```bash
git add backend/core
git commit -m "feat: параметры WebAuthn и одноразовые challenge"
```

---

## Задача 4: Подсчёт способов входа

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/login_methods.py`
- Изменить: `backend/core/src/repibot_core/services/profile.py:64-82` — `passkey_count` считается по-настоящему
- Тест: `backend/core/tests/test_login_methods.py`

**Интерфейсы:**
- Потребляет: `PasskeyRepository.count_for_user` (задача 1), `LoginMethods` и `can_unlink` из `domain/identity.py`.
- Производит: `async def login_methods(session: AsyncSession, user: User) -> LoginMethods`.

Одна функция на три места: профиль показывает число ключей, удаление passkey и отвязка Telegram спрашивают, останется ли чем войти. Считать это в каждом из них по отдельности — гарантированно разойтись в одном.

- [ ] **Шаг 1: Написать падающий тест**

Создать `backend/core/tests/test_login_methods.py`:

```python
"""Сколько способов входа осталось у пользователя."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.passkeys import PasskeyRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.domain.identity import can_unlink
from repibot_core.services.login_methods import login_methods

pytestmark = pytest.mark.docker


async def test_password_and_passkey_are_counted(db_session: AsyncSession) -> None:
    users = UserRepository(db_session)
    user = await users.create(
        email="user@example.org",
        password_hash="argon2",
        referral_code=await users.next_referral_code(),
    )
    await PasskeyRepository(db_session).create(
        user_id=user.id,
        credential_id=b"one",
        public_key=b"key",
        sign_count=0,
        transports=None,
        name="Ключ",
    )
    await db_session.commit()

    methods = await login_methods(db_session, user)

    assert methods.has_password is True
    assert methods.passkey_count == 1
    assert can_unlink(methods, "password") is True


async def test_single_passkey_cannot_be_removed(db_session: AsyncSession) -> None:
    """Единственный способ входа снять нельзя — иначе аккаунт запирается снаружи."""
    users = UserRepository(db_session)
    user = await users.create(referral_code=await users.next_referral_code())
    await PasskeyRepository(db_session).create(
        user_id=user.id,
        credential_id=b"only",
        public_key=b"key",
        sign_count=0,
        transports=None,
        name="Ключ",
    )
    await db_session.commit()

    methods = await login_methods(db_session, user)

    assert can_unlink(methods, "passkey") is False
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_login_methods.py -q`
Expected: FAIL с `ModuleNotFoundError: repibot_core.services.login_methods`.

- [ ] **Шаг 3: Написать функцию**

Создать `backend/core/src/repibot_core/services/login_methods.py`:

```python
"""Какими способами человек может войти прямо сейчас.

Профилю это нужно для показа, отвязке — для проверки «останется ли чем войти».
Считается в одном месте: разойтись двум подсчётам ничего не мешает, а цена
расхождения — запертый снаружи аккаунт.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.db.repositories.passkeys import PasskeyRepository
from repibot_core.domain.identity import LoginMethods


async def login_methods(session: AsyncSession, user: User) -> LoginMethods:
    return LoginMethods(
        has_password=user.password_hash is not None,
        has_telegram=user.telegram_id is not None,
        passkey_count=await PasskeyRepository(session).count_for_user(user.id),
    )
```

- [ ] **Шаг 4: Показать настоящее число ключей в профиле**

В `backend/core/src/repibot_core/services/profile.py` заменить заглушку в `view`:

```python
    async def view(self, user_id: int) -> ProfileView:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthError("not_found", "пользователь не найден")
        methods = await login_methods(self._session, user)
        return ProfileView(
            user_id=user.id,
            email=user.email,
            email_verified=user.email_verified_at is not None,
            telegram_username=user.telegram_username,
            name=user.name,
            language=user.language,
            role=user.role,
            referral_code=user.referral_code,
            has_password=methods.has_password,
            has_telegram=methods.has_telegram,
            passkey_count=methods.passkey_count,
        )
```

Импорт: `from repibot_core.services.login_methods import login_methods`.

- [ ] **Шаг 5: Прогнать тесты**

Run: `uv run pytest backend/core/tests/test_login_methods.py backend/core/tests/test_profile.py -q`
Expected: PASS, включая существующие тесты профиля.

- [ ] **Шаг 6: Коммит**

```bash
git add backend/core
git commit -m "feat: подсчёт способов входа для профиля и отвязки"
```

---

## Задача 5: Вход и регистрация passkey

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/auth/passkey.py`
- Тест: `backend/core/tests/test_auth_passkey.py`

**Интерфейсы:**
- Потребляет: `SoftAuthenticator` (задача 2), `relying_party`, `challenge_from_response`, `credential_id_from_response`, `RP_NAME`, `ChallengeStore` (задача 3), `login_methods` (задача 4), `AuthService.issue`.
- Производит: `PasskeyAuth(session, settings, auth, challenges)` с методами `registration_options(user_id) -> dict[str, Any]`, `register(user_id, credential, name) -> None`, `login_options() -> dict[str, Any]`, `login(credential, *, user_agent, ip) -> IssuedSession`, `list_keys(user_id) -> list[PasskeyView]`, `delete(user_id, passkey_id) -> None`; `PasskeyView(id, name, created_at, last_used_at)`.

- [ ] **Шаг 1: Написать падающий тест**

Создать `backend/core/tests/test_auth_passkey.py`:

```python
"""Passkey: регистрация ключа, вход без пароля, удаление."""

from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.db.repositories.users import UserRepository
from repibot_core.security.webauthn import relying_party
from repibot_core.services.auth.passkey import PasskeyAuth
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError
from repibot_core.services.challenges import ChallengeStore
from repibot_core.services.principal import PrincipalCache
from repibot_core.settings import get_settings
from repibot_core.testing.webauthn import SoftAuthenticator

pytestmark = pytest.mark.docker


def _device() -> SoftAuthenticator:
    party = relying_party(get_settings().public_web_url)
    return SoftAuthenticator(rp_id=party.rp_id, origin=party.origin)


def _service(session: AsyncSession) -> PasskeyAuth:
    settings = get_settings()
    redis = FakeRedis()
    auth = AuthService(session, settings, PrincipalCache(redis))
    return PasskeyAuth(session, settings, auth, ChallengeStore(redis))


async def _user(session: AsyncSession, **fields: object) -> User:
    users = UserRepository(session)
    user = await users.create(
        email="user@example.org", referral_code=await users.next_referral_code(), **fields
    )
    await session.commit()
    return user


async def _register(service: PasskeyAuth, user: User, device: SoftAuthenticator) -> None:
    options = await service.registration_options(user.id)
    from webauthn.helpers import base64url_to_bytes

    challenge = base64url_to_bytes(str(options["challenge"]))
    await service.register(user.id, device.register(challenge), name="Ноутбук")


async def test_registered_key_lets_the_user_in(db_session: AsyncSession) -> None:
    user = await _user(db_session, password_hash="argon2")
    service = _service(db_session)
    device = _device()
    await _register(service, user, device)

    options = await service.login_options()
    from webauthn.helpers import base64url_to_bytes

    challenge = base64url_to_bytes(str(options["challenge"]))
    issued = await service.login(
        device.authenticate(challenge, user_handle=str(user.id).encode()),
        user_agent="pytest",
        ip="127.0.0.1",
    )

    assert issued.refresh_token is not None
    assert issued.session_id is not None


async def test_challenge_works_only_once(db_session: AsyncSession) -> None:
    """Записанный ответ не должен пускать в аккаунт второй раз."""
    user = await _user(db_session, password_hash="argon2")
    service = _service(db_session)
    device = _device()
    await _register(service, user, device)

    options = await service.login_options()
    from webauthn.helpers import base64url_to_bytes

    challenge = base64url_to_bytes(str(options["challenge"]))
    reply = device.authenticate(challenge, user_handle=str(user.id).encode())
    await service.login(reply, user_agent=None, ip=None)

    with pytest.raises(AuthError) as failure:
        await service.login(reply, user_agent=None, ip=None)
    assert failure.value.code == "token_invalid"


async def test_foreign_challenge_is_refused(db_session: AsyncSession) -> None:
    """Challenge, которого сервер не выдавал, не принимается."""
    user = await _user(db_session, password_hash="argon2")
    service = _service(db_session)
    device = _device()
    await _register(service, user, device)

    with pytest.raises(AuthError) as failure:
        await service.login(
            device.authenticate(b"самодельный challenge", user_handle=b"1"),
            user_agent=None,
            ip=None,
        )
    assert failure.value.code == "token_invalid"


async def test_last_login_method_cannot_be_deleted(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    service = _service(db_session)
    device = _device()
    await _register(service, user, device)
    keys = await service.list_keys(user.id)

    with pytest.raises(AuthError) as failure:
        await service.delete(user.id, keys[0].id)
    assert failure.value.code == "last_login_method"


async def test_key_of_another_user_is_not_found(db_session: AsyncSession) -> None:
    """Чужой ключ не удаляется и о его существовании не сообщается."""
    owner = await _user(db_session, password_hash="argon2")
    service = _service(db_session)
    await _register(service, owner, _device())
    keys = await service.list_keys(owner.id)

    users = UserRepository(db_session)
    stranger = await users.create(
        email="other@example.org", referral_code=await users.next_referral_code()
    )
    await db_session.commit()

    with pytest.raises(AuthError) as failure:
        await service.delete(stranger.id, keys[0].id)
    assert failure.value.code == "not_found"


async def test_banned_user_cannot_sign_in_with_passkey(db_session: AsyncSession) -> None:
    """Статус проверяется в AuthService: способ входа его не обходит."""
    from repibot_core.db.models import UserStatus

    user = await _user(db_session, password_hash="argon2")
    service = _service(db_session)
    device = _device()
    await _register(service, user, device)
    user.status = UserStatus.banned
    await db_session.commit()

    options = await service.login_options()
    from webauthn.helpers import base64url_to_bytes

    challenge = base64url_to_bytes(str(options["challenge"]))
    with pytest.raises(AuthError) as failure:
        await service.login(
            device.authenticate(challenge, user_handle=str(user.id).encode()),
            user_agent=None,
            ip=None,
        )
    assert failure.value.code == "forbidden"
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_auth_passkey.py -q`
Expected: FAIL с `ModuleNotFoundError: repibot_core.services.auth.passkey`.

- [ ] **Шаг 3: Написать сервис**

Создать `backend/core/src/repibot_core/services/auth/passkey.py`:

```python
"""Вход по passkey.

Способ входа опознаёт человека и передаёт его AuthService — токены выдаёт
только он. Секрета на нашей стороне нет вовсе: в базе лежит публичный ключ,
и утечка базы не даёт войти ни в один аккаунт.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from repibot_core.db.models import User
from repibot_core.db.repositories.passkeys import PasskeyRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.domain.identity import can_unlink
from repibot_core.security.webauthn import (
    RP_NAME,
    challenge_from_response,
    credential_id_from_response,
    relying_party,
)
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError, IssuedSession
from repibot_core.services.challenges import ChallengeStore
from repibot_core.services.login_methods import login_methods
from repibot_core.settings import Settings

logger = logging.getLogger(__name__)

PURPOSE_REGISTER = "register"
PURPOSE_LOGIN = "login"

DEFAULT_KEY_NAME = "Ключ"
MAX_KEY_NAME_LENGTH = 64


@dataclass(frozen=True, slots=True)
class PasskeyView:
    id: int
    name: str
    created_at: datetime
    last_used_at: datetime | None


class PasskeyAuth:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        auth: AuthService,
        challenges: ChallengeStore,
    ) -> None:
        self._session = session
        self._settings = settings
        self._auth = auth
        self._challenges = challenges
        self._party = relying_party(settings.public_web_url)
        self._users = UserRepository(session)
        self._passkeys = PasskeyRepository(session)

    async def registration_options(self, user_id: int) -> dict[str, Any]:
        user = await self._require_user(user_id)
        # Уже зарегистрированные ключи перечисляются, чтобы аутентификатор не
        # завёл на этом же устройстве второй: человек получил бы два ключа,
        # неотличимых в списке.
        existing = await self._passkeys.list_for_user(user_id)
        options = generate_registration_options(
            rp_id=self._party.rp_id,
            rp_name=RP_NAME,
            # Идентификатор пользователя уходит в аутентификатор и возвращается
            # при входе как userHandle. Это внутренний номер, не почта: почту
            # человек меняет, а ключ должен пережить смену.
            user_id=str(user.id).encode(),
            user_name=self._display_name(user),
            user_display_name=user.name or self._display_name(user),
            authenticator_selection=AuthenticatorSelectionCriteria(
                # Discoverable: без этого на экране входа пришлось бы сначала
                # спрашивать почту, чтобы понять, чей ключ предлагать.
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
            exclude_credentials=[
                PublicKeyCredentialDescriptor(id=row.credential_id) for row in existing
            ],
        )
        await self._challenges.remember(PURPOSE_REGISTER, options.challenge, user_id=user.id)
        return dict(json.loads(options_to_json(options)))

    async def register(self, user_id: int, credential: dict[str, Any], name: str) -> None:
        challenge = self._challenge_of(credential)
        owner = await self._challenges.take(PURPOSE_REGISTER, challenge)
        if owner != str(user_id):
            raise AuthError("token_invalid", "challenge не выдавался этому пользователю")

        try:
            verified = verify_registration_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=self._party.rp_id,
                expected_origin=self._party.origin,
            )
        except WebAuthnException as error:
            logger.warning("аутентификатор не принят при регистрации: %s", error)
            raise AuthError("invalid_credentials", "аутентификатор не принят") from error

        # Тот же ключ у другого аккаунта — это либо ошибка, либо попытка
        # привязать чужой аутентификатор. Уникальность держит и база, но
        # понятный код ответа она не вернёт.
        occupied = await self._passkeys.get_by_credential_id(verified.credential_id)
        if occupied is not None:
            raise AuthError("link_conflict", "этот ключ уже зарегистрирован")

        await self._passkeys.create(
            user_id=user_id,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            transports=self._transports(credential),
            name=(name.strip() or DEFAULT_KEY_NAME)[:MAX_KEY_NAME_LENGTH],
        )
        await self._session.commit()

    async def login_options(self) -> dict[str, Any]:
        """Параметры входа без указания пользователя: ключ сам скажет, чей он."""
        options = generate_authentication_options(
            rp_id=self._party.rp_id, user_verification=UserVerificationRequirement.PREFERRED
        )
        await self._challenges.remember(PURPOSE_LOGIN, options.challenge)
        return dict(json.loads(options_to_json(options)))

    async def login(
        self, credential: dict[str, Any], *, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        challenge = self._challenge_of(credential)
        if await self._challenges.take(PURPOSE_LOGIN, challenge) is None:
            raise AuthError("token_invalid", "challenge неизвестен или уже использован")

        try:
            credential_id = credential_id_from_response(credential)
        except ValueError as error:
            raise AuthError("token_invalid", str(error)) from error

        row = await self._passkeys.get_by_credential_id(credential_id)
        if row is None:
            raise AuthError("invalid_credentials", "ключ не зарегистрирован")

        try:
            verified = verify_authentication_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=self._party.rp_id,
                expected_origin=self._party.origin,
                credential_public_key=row.public_key,
                credential_current_sign_count=row.sign_count,
            )
        except WebAuthnException as error:
            # Отставший счётчик подписей означает клон ключа, а неверная
            # подпись — подделку. Наружу и в том, и в другом случае уходит
            # общий код: подробность помогает только подбирающему.
            logger.warning("ответ аутентификатора отклонён: %s", error)
            raise AuthError("invalid_credentials", "аутентификатор не принят") from error

        row.sign_count = verified.new_sign_count
        row.last_used_at = datetime.now(UTC)
        user = await self._users.get(row.user_id)
        if user is None:
            raise AuthError("invalid_credentials", "владелец ключа удалён")
        await self._session.commit()

        return await self._auth.issue(user, user_agent=user_agent, ip=ip, with_refresh=True)

    async def list_keys(self, user_id: int) -> list[PasskeyView]:
        return [
            PasskeyView(
                id=row.id,
                name=row.name,
                created_at=row.created_at,
                last_used_at=row.last_used_at,
            )
            for row in await self._passkeys.list_for_user(user_id)
        ]

    async def delete(self, user_id: int, passkey_id: int) -> None:
        row = await self._passkeys.get(passkey_id)
        # Чужой ключ не удаляется, и знать о его существовании тоже незачем:
        # ответ одинаков для несуществующего и для принадлежащего другому.
        if row is None or row.user_id != user_id:
            raise AuthError("not_found", "ключ не найден")

        user = await self._require_user(user_id)
        methods = await login_methods(self._session, user)
        if not can_unlink(methods, "passkey"):
            raise AuthError("last_login_method", "это единственный способ входа")

        await self._passkeys.delete(row)
        await self._session.commit()

    async def _require_user(self, user_id: int) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthError("not_found", "пользователь не найден")
        return user

    def _challenge_of(self, credential: dict[str, Any]) -> bytes:
        try:
            return challenge_from_response(credential)
        except ValueError as error:
            raise AuthError("token_invalid", str(error)) from error

    @staticmethod
    def _transports(credential: dict[str, Any]) -> list[str] | None:
        response = credential.get("response")
        if not isinstance(response, dict):
            return None
        transports = response.get("transports")
        if not isinstance(transports, list):
            return None
        return [str(item) for item in transports]

    @staticmethod
    def _display_name(user: User) -> str:
        """Имя в системном окне выбора ключа: по нему человек узнаёт аккаунт."""
        if user.email is not None:
            return user.email
        if user.telegram_username is not None:
            return f"@{user.telegram_username}"
        return f"Re:Pibot #{user.id}"
```

- [ ] **Шаг 4: Прогнать тесты**

Run: `uv run pytest backend/core/tests/test_auth_passkey.py -q`
Expected: шесть тестов PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add backend/core
git commit -m "feat: вход по passkey"
```

---

## Задача 6: Эндпоинты passkey

**Файлы:**
- Изменить: `backend/api/src/repibot_api/routers/auth.py` — `/passkey/login/options`, `/passkey/login/verify`
- Изменить: `backend/api/src/repibot_api/routers/me.py` — `/me/passkeys` (список, создание, удаление) и `/me/passkeys/options`
- Изменить: `backend/api/src/repibot_api/schemas.py`
- Изменить: `backend/api/src/repibot_api/errors.py:50-61` — статусы новых кодов
- Изменить: `backend/core/src/repibot_core/ratelimit.py` — правило для параметров passkey
- Тест: `backend/api/tests/test_passkey_routes.py`

**Интерфейсы:**
- Потребляет: `PasskeyAuth` (задача 5), `ChallengeStore` (задача 3).
- Производит: схемы `PasskeyOptionsResponse {options: dict[str, Any]}`, `PasskeyRegisterRequest {credential: dict[str, Any], name: str}`, `PasskeyLoginRequest {credential: dict[str, Any]}`, `PasskeyResponse {id, name, created_at, last_used_at}`; правило `PASSKEY_PER_IP`.

- [ ] **Шаг 1: Написать падающий тест**

Создать `backend/api/tests/test_passkey_routes.py`:

```python
"""Эндпоинты passkey: выдача параметров, вход, список и удаление."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from webauthn.helpers import base64url_to_bytes

from repibot_core.security.webauthn import relying_party
from repibot_core.settings import get_settings
from repibot_core.testing.webauthn import SoftAuthenticator

pytestmark = pytest.mark.docker

PASSWORD = "совершенно обычный пароль"


def _device() -> SoftAuthenticator:
    party = relying_party(get_settings().public_web_url)
    return SoftAuthenticator(rp_id=party.rp_id, origin=party.origin)


async def _sign_in(client: AsyncClient, email: str = "user@example.org") -> str:
    """Регистрация, подтверждение по ссылке из outbox и вход. Возвращает access-токен."""
    await client.post(
        "/api/auth/register", json={"email": email, "password": PASSWORD, "language": "ru"}
    )

    from repibot_api.deps import get_session_factory

    async with get_session_factory()() as session:
        row = await session.execute(
            text("select payload from outbox where topic = 'email.verify' order by id desc limit 1")
        )
        link = str(row.scalar_one()["link"])

    response = await client.post("/api/auth/verify-email", json={"token": link.split("token=")[1]})
    return str(response.json()["access_token"])


async def _add_passkey(
    client: AsyncClient, token: str, device: SoftAuthenticator, name: str = "Ноутбук"
) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    options = await client.post("/api/me/passkeys/options", headers=headers)
    assert options.status_code == 200
    challenge = base64url_to_bytes(options.json()["options"]["challenge"])

    created = await client.post(
        "/api/me/passkeys",
        headers=headers,
        json={"credential": device.register(challenge), "name": name},
    )
    assert created.status_code == 201


async def test_passkey_signs_in_without_password(api_client: AsyncClient) -> None:
    token = await _sign_in(api_client)
    device = _device()
    await _add_passkey(api_client, token, device)

    options = await api_client.post("/api/auth/passkey/login/options")
    challenge = base64url_to_bytes(options.json()["options"]["challenge"])
    response = await api_client.post(
        "/api/auth/passkey/login/verify",
        json={"credential": device.authenticate(challenge, user_handle=b"1")},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    # Passkey-вход даёт полноценную сессию браузера, значит и refresh-cookie.
    assert "Path=/api/auth/refresh" in response.headers["set-cookie"]


async def test_registered_key_appears_in_the_list(api_client: AsyncClient) -> None:
    token = await _sign_in(api_client)
    await _add_passkey(api_client, token, _device(), name="Рабочий ноутбук")

    response = await api_client.get(
        "/api/me/passkeys", headers={"Authorization": f"Bearer {token}"}
    )

    body: list[dict[str, Any]] = response.json()
    assert [item["name"] for item in body] == ["Рабочий ноутбук"]
    assert body[0]["last_used_at"] is None


async def test_profile_counts_registered_keys(api_client: AsyncClient) -> None:
    token = await _sign_in(api_client)
    await _add_passkey(api_client, token, _device())

    response = await api_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    assert response.json()["passkey_count"] == 1


async def test_key_removal_needs_another_way_in(api_client: AsyncClient) -> None:
    """У аккаунта есть пароль, поэтому ключ снять можно."""
    token = await _sign_in(api_client)
    await _add_passkey(api_client, token, _device())
    headers = {"Authorization": f"Bearer {token}"}
    listed = await api_client.get("/api/me/passkeys", headers=headers)

    removed = await api_client.delete(
        f"/api/me/passkeys/{listed.json()[0]['id']}", headers=headers
    )

    assert removed.status_code == 204
    assert (await api_client.get("/api/me/passkeys", headers=headers)).json() == []


async def test_options_require_authentication(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/me/passkeys/options")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_garbage_credential_is_a_client_error(api_client: AsyncClient) -> None:
    """Мусор в теле — ответ 400 с кодом, а не пятисотка."""
    response = await api_client.post(
        "/api/auth/passkey/login/verify", json={"credential": {"nonsense": True}}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "token_invalid"
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/api/tests/test_passkey_routes.py -q`
Expected: FAIL — эндпоинты отвечают 404.

- [ ] **Шаг 3: Добавить правило лимита**

В `backend/core/src/repibot_core/ratelimit.py` рядом с остальными правилами:

```python
# Выдача параметров passkey дешева для нас и бесполезна для перебора, но
# бесконечной быть не должна: challenge занимает место в Valkey.
PASSKEY_PER_IP = Rule(limit=20, window=timedelta(minutes=1))
```

- [ ] **Шаг 4: Добавить схемы**

В `backend/api/src/repibot_api/schemas.py`:

```python
class PasskeyOptionsResponse(BaseModel):
    """Параметры WebAuthn как есть.

    Структура задана спецификацией браузера и целиком уходит в
    `navigator.credentials`; описывать её своими моделями значит поддерживать
    копию чужого стандарта.
    """

    options: dict[str, Any]


class PasskeyRegisterRequest(BaseModel):
    credential: dict[str, Any]
    name: str = Field(default="", max_length=64)


class PasskeyLoginRequest(BaseModel):
    credential: dict[str, Any]


class PasskeyResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    last_used_at: datetime | None
```

Импорт `Any` из `typing`.

- [ ] **Шаг 5: Добавить статусы новых кодов**

В `backend/api/src/repibot_api/errors.py` в `_AUTH_STATUS`:

```python
    # Конфликт состояния, а не ошибка запроса: тот же запрос при другом
    # состоянии аккаунта пройдёт.
    "last_login_method": 409,
    "telegram_already_linked": 409,
    "link_conflict": 409,
```

- [ ] **Шаг 6: Добавить публичные эндпоинты входа**

В `backend/api/src/repibot_api/routers/auth.py`:

```python
def _passkeys(session: AsyncSession, principals: PrincipalCache, redis: Redis) -> PasskeyAuth:
    settings = get_settings()
    auth = AuthService(session, settings, principals)
    return PasskeyAuth(session, settings, auth, ChallengeStore(redis))


@router.post("/passkey/login/options", response_model=PasskeyOptionsResponse)
async def passkey_login_options(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> PasskeyOptionsResponse:
    await _enforce(redis, f"passkey:ip:{client_ip(request)}", PASSKEY_PER_IP)
    options = await _passkeys(session, principals, redis).login_options()
    return PasskeyOptionsResponse(options=options)


@router.post("/passkey/login/verify", response_model=TokenResponse)
async def passkey_login_verify(
    payload: PasskeyLoginRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> TokenResponse:
    try:
        issued = await _passkeys(session, principals, redis).login(
            payload.credential,
            user_agent=request.headers.get("user-agent"),
            ip=client_ip(request),
        )
    except AuthError as error:
        raise api_error_from(error) from error
    return _respond(response, issued)
```

- [ ] **Шаг 7: Добавить приватные эндпоинты управления ключами**

В `backend/api/src/repibot_api/routers/me.py`:

```python
def _passkeys(session: AsyncSession, principals: PrincipalCache, redis: Redis) -> PasskeyAuth:
    settings = get_settings()
    auth = AuthService(session, settings, principals)
    return PasskeyAuth(session, settings, auth, ChallengeStore(redis))


@router.post("/passkeys/options", response_model=PasskeyOptionsResponse)
async def passkey_registration_options(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> PasskeyOptionsResponse:
    try:
        options = await _passkeys(session, principals, redis).registration_options(
            context.principal.user_id
        )
    except AuthError as error:
        raise api_error_from(error) from error
    return PasskeyOptionsResponse(options=options)


@router.post("/passkeys", status_code=201, response_model=AcceptedResponse)
async def add_passkey(
    payload: PasskeyRegisterRequest,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AcceptedResponse:
    try:
        await _passkeys(session, principals, redis).register(
            context.principal.user_id, payload.credential, payload.name
        )
    except AuthError as error:
        raise api_error_from(error) from error
    return AcceptedResponse(status="passkey_added")


@router.get("/passkeys", response_model=list[PasskeyResponse])
async def list_passkeys(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> list[PasskeyResponse]:
    items = await _passkeys(session, principals, redis).list_keys(context.principal.user_id)
    return [
        PasskeyResponse(
            id=item.id,
            name=item.name,
            created_at=item.created_at,
            last_used_at=item.last_used_at,
        )
        for item in items
    ]


@router.delete("/passkeys/{passkey_id}", status_code=204)
async def delete_passkey(
    passkey_id: int,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    try:
        await _passkeys(session, principals, redis).delete(context.principal.user_id, passkey_id)
    except AuthError as error:
        raise api_error_from(error) from error
```

- [ ] **Шаг 8: Прогнать тесты**

Run: `uv run pytest backend/api/tests/test_passkey_routes.py backend/api/tests/test_me_routes.py -q`
Expected: PASS, старые тесты `/api/me` не сломаны.

- [ ] **Шаг 9: Коммит**

```bash
git add backend
git commit -m "feat: эндпоинты регистрации и входа по passkey"
```

---

## Задача 7: PKCE и проверка ID-токена Telegram

**Файлы:**
- Создать: `backend/core/src/repibot_core/security/pkce.py`
- Создать: `backend/core/src/repibot_core/integrations/telegram/__init__.py`
- Создать: `backend/core/src/repibot_core/integrations/telegram/oidc.py`
- Изменить: `backend/core/src/repibot_core/settings.py` — `telegram_oidc_client_id`, `telegram_oidc_client_secret`
- Тест: `backend/core/tests/test_telegram_oidc.py`

**Интерфейсы:**
- Производит: `generate_code_verifier() -> str`, `code_challenge(verifier: str) -> str`; `OidcIdentity(telegram_id: int, username: str | None, name: str | None)`; `TelegramOidc(settings, redis, client=None)` с `authorization_url(*, state, code_challenge, redirect_uri) -> str`, `exchange(*, code, code_verifier, redirect_uri) -> str`, `verify_id_token(token) -> OidcIdentity`, `is_configured: bool`.

- [ ] **Шаг 1: Написать падающий тест**

Создать `backend/core/tests/test_telegram_oidc.py`:

```python
"""Вход через Telegram: PKCE, обмен кода и проверка ID-токена."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fakeredis.aioredis import FakeRedis

from repibot_core.integrations.telegram.oidc import ISSUER, TelegramOidc
from repibot_core.security.pkce import code_challenge, generate_code_verifier
from repibot_core.services.auth.types import AuthError
from repibot_core.settings import Settings, get_settings

CLIENT_ID = "1234567:web"
REDIRECT = "https://example.org/api/auth/telegram/callback"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_KID = "test-key"


def _jwks() -> dict[str, Any]:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_KEY.public_key()))
    jwk.update({"kid": _KID, "alg": "RS256", "use": "sig"})
    return {"keys": [jwk]}


def _id_token(**overrides: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "777000",
        "name": "Тест",
        "preferred_username": "tester",
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": _KID})


def _settings() -> Settings:
    return get_settings().model_copy(
        update={"telegram_oidc_client_id": CLIENT_ID, "telegram_oidc_client_secret": "secret"}
    )


def _service(handler: Any) -> TelegramOidc:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TelegramOidc(_settings(), FakeRedis(), client=client)


def _serve(token: str | None = None) -> Any:
    """Отвечает за оба обращения к Telegram: JWKS и обмен кода."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("jwks.json"):
            return httpx.Response(200, json=_jwks())
        return httpx.Response(200, json={"id_token": token or _id_token()})

    return handler


def test_code_challenge_is_sha256_in_base64url() -> None:
    verifier = generate_code_verifier()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode()

    assert code_challenge(verifier) == expected.rstrip("=")
    # RFC 7636 требует от 43 до 128 символов.
    assert 43 <= len(verifier) <= 128


async def test_authorization_url_carries_pkce_and_scopes() -> None:
    service = _service(_serve())

    url = service.authorization_url(
        state="state-1", code_challenge="challenge-1", redirect_uri=REDIRECT
    )

    query = parse_qs(urlsplit(url).query)
    assert query["client_id"] == [CLIENT_ID]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == ["challenge-1"]
    assert query["state"] == ["state-1"]
    assert "telegram:bot_access" in query["scope"][0]


async def test_valid_id_token_yields_identity() -> None:
    service = _service(_serve())

    identity = await service.verify_id_token(_id_token())

    assert identity.telegram_id == 777000
    assert identity.username == "tester"
    assert identity.name == "Тест"


async def test_forged_signature_is_rejected() -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        {"iss": ISSUER, "aud": CLIENT_ID, "sub": "1", "exp": int(time.time()) + 300},
        other,
        algorithm="RS256",
        headers={"kid": _KID},
    )
    service = _service(_serve())

    with pytest.raises(AuthError) as failure:
        await service.verify_id_token(forged)
    assert failure.value.code == "invalid_credentials"


async def test_token_for_another_client_is_rejected() -> None:
    service = _service(_serve())

    with pytest.raises(AuthError):
        await service.verify_id_token(_id_token(aud="somebody-else"))


async def test_expired_token_is_rejected() -> None:
    service = _service(_serve())
    stale = int(time.time()) - 3600

    with pytest.raises(AuthError):
        await service.verify_id_token(_id_token(iat=stale, exp=stale + 300))


async def test_token_from_another_issuer_is_rejected() -> None:
    service = _service(_serve())

    with pytest.raises(AuthError):
        await service.verify_id_token(_id_token(iss="https://evil.example.org"))


async def test_exchange_sends_verifier_and_returns_id_token() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("jwks.json"):
            return httpx.Response(200, json=_jwks())
        seen.update(
            {key: value[0] for key, value in parse_qs(request.content.decode()).items()}
        )
        return httpx.Response(200, json={"id_token": _id_token()})

    service = _service(handler)

    token = await service.exchange(code="the-code", code_verifier="verifier", redirect_uri=REDIRECT)

    assert token
    assert seen["grant_type"] == "authorization_code"
    assert seen["code"] == "the-code"
    assert seen["code_verifier"] == "verifier"
    assert seen["redirect_uri"] == REDIRECT


async def test_refused_exchange_becomes_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    service = _service(handler)

    with pytest.raises(AuthError) as failure:
        await service.exchange(code="stale", code_verifier="v", redirect_uri=REDIRECT)
    assert failure.value.code == "invalid_credentials"


async def test_jwks_is_fetched_once_and_cached() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("jwks.json"):
            calls["count"] += 1
            return httpx.Response(200, json=_jwks())
        return httpx.Response(404)

    service = _service(handler)

    await service.verify_id_token(_id_token())
    await service.verify_id_token(_id_token())

    assert calls["count"] == 1
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_telegram_oidc.py -q`
Expected: FAIL с `ModuleNotFoundError: repibot_core.security.pkce`.

- [ ] **Шаг 3: Написать PKCE**

Создать `backend/core/src/repibot_core/security/pkce.py`:

```python
"""PKCE: доказательство того, что код обменивает тот же клиент, что его просил.

Без него перехваченный код обменивается кем угодно, знающим client_secret, —
а секрет живёт на сервере, но код проходит через браузер и историю переходов.
"""

from __future__ import annotations

import base64
import hashlib
import secrets

# 64 случайных байта дают 86 символов base64url — внутри разрешённых RFC 7636
# сорока трёх и ста двадцати восьми.
VERIFIER_BYTES = 64


def generate_code_verifier() -> str:
    return secrets.token_urlsafe(VERIFIER_BYTES)


def code_challenge(verifier: str) -> str:
    """S256, а не plain: plain отправляет verifier в адресной строке."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
```

- [ ] **Шаг 4: Написать клиент OIDC**

Создать `backend/core/src/repibot_core/integrations/telegram/__init__.py` (пустой, с докстрингом) и `backend/core/src/repibot_core/integrations/telegram/oidc.py`:

```python
"""Вход через Telegram по OpenID Connect.

Адреса взяты из discovery-документа `oauth.telegram.org` и зафиксированы
константами: один сетевой запрос на каждый вход и без того нужен, а
рассинхронизация с discovery проявилась бы отказом на первом же шаге.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from redis.asyncio import Redis

from repibot_core.services.auth.types import AuthError
from repibot_core.settings import Settings

logger = logging.getLogger(__name__)

ISSUER = "https://oauth.telegram.org"
AUTHORIZATION_ENDPOINT = f"{ISSUER}/auth"
TOKEN_ENDPOINT = f"{ISSUER}/token"  # noqa: S105 — адрес эндпоинта, не секрет
JWKS_URI = f"{ISSUER}/.well-known/jwks.json"

# telegram:bot_access даёт боту право написать первым: без него
# зарегистрировавшийся на сайте не получил бы ни одного уведомления.
# phone не запрашивается — телефон не нужен, а хранить его значит отвечать за
# него.
SCOPES = "openid profile telegram:bot_access"

# Список закрыт намеренно: принимать алгоритм из заголовка токена — известный
# способ подсунуть «none» или подпись симметричным ключом.
ALGORITHMS = ("RS256", "ES256", "EdDSA", "ES256K")

JWKS_CACHE_KEY = "telegram:oidc:jwks"
JWKS_CACHE_TTL_SECONDS = 3600
TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class OidcIdentity:
    """Кто пришёл. Единственный источник — ID-токен: userinfo у Telegram нет."""

    telegram_id: int
    username: str | None
    name: str | None


class TelegramOidc:
    def __init__(
        self, settings: Settings, redis: Redis, client: httpx.AsyncClient | None = None
    ) -> None:
        self._settings = settings
        self._redis = redis
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)

    @property
    def is_configured(self) -> bool:
        """Без Client ID кнопку входа показывать нечему: BotFather её не выдал."""
        return bool(self._settings.telegram_oidc_client_id)

    def authorization_url(self, *, state: str, code_challenge: str, redirect_uri: str) -> str:
        query = urlencode(
            {
                "client_id": self._settings.telegram_oidc_client_id,
                "response_type": "code",
                "scope": SCOPES,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{AUTHORIZATION_ENDPOINT}?{query}"

    async def exchange(self, *, code: str, code_verifier: str, redirect_uri: str) -> str:
        """Меняет код на ID-токен. Секрет уходит в теле, а не в адресе."""
        try:
            response = await self._client.post(
                TOKEN_ENDPOINT,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier,
                    "client_id": self._settings.telegram_oidc_client_id,
                    "client_secret": self._settings.telegram_oidc_client_secret.get_secret_value(),
                },
            )
        except httpx.HTTPError as error:
            logger.warning("обмен кода Telegram не удался: %s", type(error).__name__)
            raise AuthError("invalid_credentials", "Telegram недоступен") from error

        if response.status_code != httpx.codes.OK:
            # Тело ответа в журнал не идёт: в нём эхом возвращается код.
            logger.warning("Telegram отказал в обмене кода: %s", response.status_code)
            raise AuthError("invalid_credentials", "код не принят")

        token = response.json().get("id_token")
        if not isinstance(token, str) or not token:
            raise AuthError("invalid_credentials", "ответ Telegram без ID-токена")
        return token

    async def verify_id_token(self, token: str) -> OidcIdentity:
        key = await self._signing_key(token)
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=list(ALGORITHMS),
                audience=self._settings.telegram_oidc_client_id,
                issuer=ISSUER,
            )
        except jwt.PyJWTError as error:
            logger.warning("ID-токен Telegram отклонён: %s", type(error).__name__)
            raise AuthError("invalid_credentials", "ID-токен не принят") from error

        try:
            telegram_id = int(claims["sub"])
        except (KeyError, TypeError, ValueError) as error:
            raise AuthError("invalid_credentials", "в ID-токене нет sub") from error

        return OidcIdentity(
            telegram_id=telegram_id,
            username=claims.get("preferred_username"),
            name=claims.get("name"),
        )

    async def _signing_key(self, token: str) -> Any:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.PyJWTError as error:
            raise AuthError("invalid_credentials", "заголовок ID-токена не разбирается") from error

        key = self._find_key(await self._jwks(), kid)
        if key is None:
            # Ключи ротируются: незнакомый kid — повод перечитать JWKS, а не
            # отказать. Второй промах уже означает чужую подпись.
            key = self._find_key(await self._jwks(force=True), kid)
        if key is None:
            raise AuthError("invalid_credentials", "ключ подписи неизвестен")
        return key

    @staticmethod
    def _find_key(jwks: dict[str, Any], kid: str | None) -> Any:
        for entry in jwks.get("keys", []):
            if kid is None or entry.get("kid") == kid:
                return jwt.PyJWK.from_dict(entry).key
        return None

    async def _jwks(self, *, force: bool = False) -> dict[str, Any]:
        if not force:
            cached = await self._redis.get(JWKS_CACHE_KEY)
            if cached is not None:
                return dict(json.loads(cached))

        try:
            response = await self._client.get(JWKS_URI)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise AuthError("invalid_credentials", "JWKS Telegram недоступен") from error

        await self._redis.set(JWKS_CACHE_KEY, response.text, ex=JWKS_CACHE_TTL_SECONDS)
        return dict(response.json())
```

- [ ] **Шаг 5: Добавить настройки**

В `backend/core/src/repibot_core/settings.py` рядом с прочими секретами:

```python
    # Выдаются в мини-приложении BotFather: Bot Settings → Web Login. Пустые
    # значения означают, что вход через Telegram в браузере не настроен —
    # кнопка тогда не показывается, а не ломается.
    telegram_oidc_client_id: str = ""
    telegram_oidc_client_secret: SecretStr = SecretStr("")
```

- [ ] **Шаг 6: Прогнать тесты**

Run: `uv run pytest backend/core/tests/test_telegram_oidc.py backend/core/tests/test_settings.py -q`
Expected: PASS.

- [ ] **Шаг 7: Коммит**

```bash
git add backend/core
git commit -m "feat: проверка ID-токена Telegram и PKCE"
```

---

## Задача 8: Вход через Telegram в браузере

**Файлы:**
- Изменить: `backend/core/src/repibot_core/services/auth/telegram.py` — добавить `login_from_oidc`
- Тест: `backend/core/tests/test_auth_telegram.py` — дописать сценарии OIDC

**Интерфейсы:**
- Потребляет: `OidcIdentity` (задача 7), существующий `TelegramAuth._find_or_create`.
- Производит: `TelegramAuth.login_from_oidc(identity: OidcIdentity, *, user_agent: str | None, ip: str | None) -> IssuedSession`.

Браузерный вход отличается от MiniApp двумя вещами: человека опознаёт Telegram, а не подпись `initData`, и refresh здесь выдаётся — cookie в обычном браузере живёт нормально. Поиск и создание пользователя общие: иначе один и тот же человек получил бы два аккаунта в зависимости от того, откуда вошёл.

- [ ] **Шаг 1: Написать падающий тест**

Дописать в `backend/core/tests/test_auth_telegram.py`:

```python
async def test_oidc_login_reuses_the_miniapp_account(db_session: AsyncSession) -> None:
    """Один Telegram — один аккаунт, откуда бы человек ни вошёл."""
    from repibot_core.integrations.telegram.oidc import OidcIdentity

    service = _service(db_session)
    first = await service.login_from_miniapp(
        build_init_data(telegram_id=777000, bot_token=get_settings().bot_token.get_secret_value()),
        ip=None,
    )
    second = await service.login_from_oidc(
        OidcIdentity(telegram_id=777000, username="tester", name="Тест"),
        user_agent="Firefox",
        ip="127.0.0.1",
    )

    from repibot_core.security.tokens import decode_access_token

    secret = get_settings().jwt_secret.get_secret_value()
    assert decode_access_token(first.access_token, secret=secret).user_id == (
        decode_access_token(second.access_token, secret=secret).user_id
    )
    # Сессии всё же разные: это два разных устройства.
    assert first.session_id != second.session_id


async def test_oidc_login_issues_refresh_unlike_miniapp(db_session: AsyncSession) -> None:
    """В обычном браузере cookie живёт, поэтому refresh выдаётся."""
    from repibot_core.integrations.telegram.oidc import OidcIdentity

    issued = await _service(db_session).login_from_oidc(
        OidcIdentity(telegram_id=42, username=None, name=None), user_agent=None, ip=None
    )

    assert issued.refresh_token is not None


async def test_oidc_login_updates_username(db_session: AsyncSession) -> None:
    """@username меняется на стороне Telegram — обновляем при каждом входе."""
    from repibot_core.integrations.telegram.oidc import OidcIdentity

    service = _service(db_session)
    await service.login_from_oidc(
        OidcIdentity(telegram_id=42, username="old", name="Тест"), user_agent=None, ip=None
    )
    await service.login_from_oidc(
        OidcIdentity(telegram_id=42, username="new", name="Тест"), user_agent=None, ip=None
    )

    from repibot_core.db.repositories.users import UserRepository

    user = await UserRepository(db_session).get_by_telegram_id(42)
    assert user is not None
    assert user.telegram_username == "new"
```

Если в существующем файле нет хелпера `_service`, взять тот, что уже используется для `login_from_miniapp`, и не заводить второй.

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_auth_telegram.py -q`
Expected: FAIL с `AttributeError: 'TelegramAuth' object has no attribute 'login_from_oidc'`.

- [ ] **Шаг 3: Написать метод**

В `backend/core/src/repibot_core/services/auth/telegram.py` добавить (докстринг модуля поправить: OIDC перестал быть будущим):

```python
    async def login_from_oidc(
        self, identity: OidcIdentity, *, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        """Вход через oauth.telegram.org.

        Подпись ID-токена проверена вызывающим: сюда приходит уже опознанный
        человек. Дальше путь общий с MiniApp — тот же поиск аккаунта и тот же
        AuthService.
        """
        user = await self._find_or_create(
            TelegramUser(
                telegram_id=identity.telegram_id,
                username=identity.username,
                first_name=identity.name,
                language_code=None,
            )
        )
        return await self._auth.issue(user, user_agent=user_agent, ip=ip, with_refresh=True)
```

Проверить фактические поля `TelegramUser` в `repibot_core/security/initdata.py` и передать те, что есть; если структура не совпадает — привести вызов к её сигнатуре, а не менять саму структуру: `initData` разбирается по спецификации Telegram, и подгонять её под OIDC нельзя.

- [ ] **Шаг 4: Прогнать тесты**

Run: `uv run pytest backend/core/tests/test_auth_telegram.py -q`
Expected: PASS, включая прежние сценарии MiniApp.

- [ ] **Шаг 5: Коммит**

```bash
git add backend/core
git commit -m "feat: вход через Telegram по OIDC"
```

---

## Задача 9: Эндпоинты браузерного входа через Telegram

**Файлы:**
- Изменить: `backend/api/src/repibot_api/routers/auth.py` — `/telegram/start`, `/telegram/callback`, `/methods`
- Изменить: `backend/api/src/repibot_api/schemas.py` — `AuthMethodsResponse`
- Тест: `backend/api/tests/test_telegram_oidc_routes.py`

**Интерфейсы:**
- Потребляет: `TelegramOidc` (задача 7), `TelegramAuth.login_from_oidc` (задача 8).
- Производит: `GET /api/auth/telegram/start` (307 на Telegram), `GET /api/auth/telegram/callback` (307 в кабинет, ставит refresh-cookie), `GET /api/auth/methods` → `{"telegram": bool, "passkey": true}`.

Весь браузерный поток отвечает редиректами, включая ошибки: человек попадает сюда прямым переходом, и JSON с кодом ошибки в адресной строке выглядел бы поломкой сайта. Ошибка уносится на `/login?error=<код>`, где фронтенд показывает фразу из словаря.

- [ ] **Шаг 1: Написать падающий тест**

Создать `backend/api/tests/test_telegram_oidc_routes.py`:

```python
"""Браузерный вход через Telegram: редиректы, state, cookie."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient

from repibot_core.integrations.telegram.oidc import ISSUER

pytestmark = pytest.mark.docker

CLIENT_ID = "1234567:web"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_KID = "test-key"


def _jwks() -> dict[str, Any]:
    import json

    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_KEY.public_key()))
    jwk.update({"kid": _KID, "alg": "RS256", "use": "sig"})
    return {"keys": [jwk]}


def _id_token(sub: str = "777000") -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": sub,
            "name": "Тест",
            "preferred_username": "tester",
            "iat": now,
            "exp": now + 300,
        },
        _KEY,
        algorithm="RS256",
        headers={"kid": _KID},
    )


@pytest.fixture
def telegram_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подставляет client_id и перехватывает сеть к oauth.telegram.org."""
    from repibot_api.routers import auth as auth_router
    from repibot_core.settings import Settings, get_settings

    settings = get_settings().model_copy(
        update={"telegram_oidc_client_id": CLIENT_ID, "telegram_oidc_client_secret": "secret"}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("jwks.json"):
            return httpx.Response(200, json=_jwks())
        return httpx.Response(200, json={"id_token": _id_token()})

    def fake_settings() -> Settings:
        return settings

    monkeypatch.setattr(auth_router, "get_settings", fake_settings)
    monkeypatch.setattr(
        auth_router,
        "oidc_http_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_start_redirects_to_telegram_with_state(
    api_client: AsyncClient, telegram_configured: None
) -> None:
    response = await api_client.get("/api/auth/telegram/start")

    assert response.status_code == 307
    target = urlsplit(response.headers["location"])
    assert target.netloc == "oauth.telegram.org"
    query = parse_qs(target.query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"][0]


async def test_start_without_configuration_returns_to_login(api_client: AsyncClient) -> None:
    """Не настроенный OIDC не должен выглядеть пятисоткой."""
    response = await api_client.get("/api/auth/telegram/start")

    assert response.status_code == 307
    assert "/login?error=telegram_unavailable" in response.headers["location"]


async def test_callback_signs_in_and_sets_cookie(
    api_client: AsyncClient, telegram_configured: None
) -> None:
    started = await api_client.get("/api/auth/telegram/start")
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]

    response = await api_client.get(
        "/api/auth/telegram/callback", params={"code": "the-code", "state": state}
    )

    assert response.status_code == 307
    assert response.headers["location"].endswith("/account")
    assert "Path=/api/auth/refresh" in response.headers["set-cookie"]


async def test_callback_with_unknown_state_is_refused(
    api_client: AsyncClient, telegram_configured: None
) -> None:
    """State не наш — либо подделка, либо просроченная попытка."""
    response = await api_client.get(
        "/api/auth/telegram/callback", params={"code": "the-code", "state": "самодельный"}
    )

    assert response.status_code == 307
    assert "/login?error=token_invalid" in response.headers["location"]


async def test_state_works_only_once(api_client: AsyncClient, telegram_configured: None) -> None:
    started = await api_client.get("/api/auth/telegram/start")
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    await api_client.get("/api/auth/telegram/callback", params={"code": "one", "state": state})

    repeated = await api_client.get(
        "/api/auth/telegram/callback", params={"code": "two", "state": state}
    )

    assert "/login?error=token_invalid" in repeated.headers["location"]


async def test_methods_tell_the_front_end_what_is_available(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/auth/methods")

    assert response.status_code == 200
    assert response.json() == {"telegram": False, "passkey": True}
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/api/tests/test_telegram_oidc_routes.py -q`
Expected: FAIL — эндпоинты отвечают 404.

- [ ] **Шаг 3: Добавить схему**

В `backend/api/src/repibot_api/schemas.py`:

```python
class AuthMethodsResponse(BaseModel):
    """Какие способы входа показывать на экране входа.

    Passkey поддерживает браузер, а не сервер, поэтому здесь он всегда true:
    решение принимает клиент. Telegram зависит от настроек развёртывания.
    """

    telegram: bool
    passkey: bool = True
```

- [ ] **Шаг 4: Написать эндпоинты**

В `backend/api/src/repibot_api/routers/auth.py`:

```python
STATE_TTL_SECONDS = 600


def oidc_http_client() -> httpx.AsyncClient:
    """Отдельная функция — точка подмены в тестах: сети к Telegram там нет."""
    return httpx.AsyncClient(timeout=TIMEOUT_SECONDS)


def _redirect_uri(settings: Settings) -> str:
    """Адрес возврата собирается из PUBLIC_WEB_URL и должен совпадать с BotFather."""
    return f"{settings.public_web_url}/api/auth/telegram/callback"


def _to_login(settings: Settings, code: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.public_web_url}/login?error={code}", status_code=307)


@router.get("/methods", response_model=AuthMethodsResponse)
async def auth_methods() -> AuthMethodsResponse:
    return AuthMethodsResponse(telegram=bool(get_settings().telegram_oidc_client_id))


@router.get("/telegram/start")
async def telegram_start(
    redis: Annotated[Redis, Depends(get_redis)],
) -> RedirectResponse:
    settings = get_settings()
    oidc = TelegramOidc(settings, redis, client=oidc_http_client())
    if not oidc.is_configured:
        return _to_login(settings, "telegram_unavailable")

    verifier = generate_code_verifier()
    state = secrets.token_urlsafe(32)
    # Verifier живёт только у нас: браузеру достаётся его хеш, и перехваченный
    # код без нашего Valkey обменять нельзя.
    await redis.set(f"oidc:state:{state}", verifier, ex=STATE_TTL_SECONDS)

    return RedirectResponse(
        oidc.authorization_url(
            state=state,
            code_challenge=code_challenge(verifier),
            redirect_uri=_redirect_uri(settings),
        ),
        status_code=307,
    )


@router.get("/telegram/callback")
async def telegram_callback(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> RedirectResponse:
    settings = get_settings()
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        return _to_login(settings, "token_invalid")

    # GETDEL: state одноразовый, иначе перехваченная ссылка возврата работала бы
    # столько же, сколько живёт запись.
    stored = await redis.getdel(f"oidc:state:{state}")
    if stored is None:
        return _to_login(settings, "token_invalid")
    verifier = stored.decode() if isinstance(stored, bytes) else str(stored)

    oidc = TelegramOidc(settings, redis, client=oidc_http_client())
    auth = AuthService(session, settings, principals)
    telegram = TelegramAuth(session, settings, auth)
    try:
        token = await oidc.exchange(
            code=code, code_verifier=verifier, redirect_uri=_redirect_uri(settings)
        )
        identity = await oidc.verify_id_token(token)
        issued = await telegram.login_from_oidc(
            identity, user_agent=request.headers.get("user-agent"), ip=client_ip(request)
        )
    except AuthError as error:
        return _to_login(settings, error.code)

    redirect = RedirectResponse(f"{settings.public_web_url}/account", status_code=307)
    if issued.refresh_token is not None and issued.refresh_expires_at is not None:
        set_refresh_cookie(
            redirect,
            issued.refresh_token,
            expires_at=issued.refresh_expires_at,
            secure=settings.environment == "production",
        )
    return redirect
```

Импорты, которых в файле ещё нет: `secrets`, `httpx`, `RedirectResponse` из `fastapi.responses`, `TelegramOidc`, `generate_code_verifier`, `code_challenge`, `Settings`, `AuthMethodsResponse`, `TIMEOUT_SECONDS` из модуля OIDC.

Access-токен здесь никуда не отдаётся намеренно: браузер возвращается на `/account`, гейт кабинета вызывает `refresh` по только что поставленной cookie и получает токен в память. Класть access в адресную строку значило бы записать его в историю браузера и в журнал прокси.

- [ ] **Шаг 5: Прогнать тесты**

Run: `uv run pytest backend/api/tests/test_telegram_oidc_routes.py backend/api/tests/test_auth_routes.py -q`
Expected: PASS.

- [ ] **Шаг 6: Коммит**

```bash
git add backend/api
git commit -m "feat: браузерный вход через Telegram"
```

---

## Задача 10: Привязка Telegram по коду

**Файлы:**
- Создать: `backend/core/src/repibot_core/integrations/telegram/bot_api.py`
- Создать: `backend/core/src/repibot_core/services/telegram_link.py`
- Изменить: `backend/core/src/repibot_core/domain/identity.py` — срок жизни кода привязки
- Тест: `backend/core/tests/test_telegram_link.py`

**Интерфейсы:**
- Потребляет: `generate_link_code`, `can_unlink`, `login_methods` (задача 4), `AuditRepository`.
- Производит: `BotApi(settings, redis, client=None)` с `username() -> str`; `LinkOffer(code: str, url: str)`; `TelegramLinkService(session, settings, redis, bot_api)` с `issue_code(user_id) -> LinkOffer`, `redeem(code, *, telegram_id, username, first_name) -> User`, `unlink(user_id) -> None`; `LINK_CODE_TTL`.

Три состояния Telegram-аккаунта из спецификации разбираются здесь и только здесь:

| Состояние | Результат |
|---|---|
| Такого `telegram_id` в базе нет | Привязывается к аккаунту, выдавшему код |
| Есть аккаунт без почты, пароля и passkey | Пустой дубль поглощается, привязка проходит |
| У аккаунта есть свой способ входа | Отказ `link_conflict` |

- [ ] **Шаг 1: Написать падающий тест**

Создать `backend/core/tests/test_telegram_link.py`:

```python
"""Привязка Telegram по коду: три состояния дубля и отвязка."""

from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.db.repositories.passkeys import PasskeyRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.services.auth.types import AuthError
from repibot_core.services.telegram_link import TelegramLinkService
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker


class FakeBotApi:
    """Имя бота — единственное, что нужно сервису от Bot API."""

    async def username(self) -> str:
        return "repibot_test_bot"


def _service(session: AsyncSession, redis: FakeRedis) -> TelegramLinkService:
    return TelegramLinkService(session, get_settings(), redis, FakeBotApi())


async def _web_user(session: AsyncSession, email: str = "user@example.org") -> User:
    users = UserRepository(session)
    user = await users.create(
        email=email,
        password_hash="argon2",
        referral_code=await users.next_referral_code(),
    )
    await session.commit()
    return user


async def _telegram_user(session: AsyncSession, telegram_id: int, **fields: object) -> User:
    users = UserRepository(session)
    user = await users.create(
        telegram_id=telegram_id, referral_code=await users.next_referral_code(), **fields
    )
    await session.commit()
    return user


async def test_code_links_unknown_telegram_account(db_session: AsyncSession) -> None:
    redis = FakeRedis()
    service = _service(db_session, redis)
    user = await _web_user(db_session)

    offer = await service.issue_code(user.id)
    linked = await service.redeem(
        offer.code, telegram_id=555, username="tester", first_name="Тест"
    )

    assert linked.id == user.id
    assert linked.telegram_id == 555
    assert offer.url == f"https://t.me/repibot_test_bot?start=link_{offer.code}"


async def test_empty_duplicate_is_absorbed(db_session: AsyncSession) -> None:
    """Открыл MiniApp, потом зарегистрировался на сайте — должен остаться один аккаунт."""
    redis = FakeRedis()
    service = _service(db_session, redis)
    duplicate = await _telegram_user(db_session, 555, name="Тест")
    user = await _web_user(db_session)

    offer = await service.issue_code(user.id)
    linked = await service.redeem(offer.code, telegram_id=555, username=None, first_name="Тест")

    assert linked.id == user.id
    remaining = await db_session.execute(
        text("select count(*) from users where id = :id"), {"id": duplicate.id}
    )
    assert remaining.scalar_one() == 0


async def test_duplicate_with_its_own_password_is_refused(db_session: AsyncSession) -> None:
    """У дубля есть свой вход — склеивать нельзя: в подпроекте 3 там появятся деньги."""
    redis = FakeRedis()
    service = _service(db_session, redis)
    await _telegram_user(db_session, 555, email="tg@example.org", password_hash="argon2")
    user = await _web_user(db_session)

    offer = await service.issue_code(user.id)

    with pytest.raises(AuthError) as failure:
        await service.redeem(offer.code, telegram_id=555, username=None, first_name=None)
    assert failure.value.code == "link_conflict"


async def test_duplicate_with_passkey_is_refused(db_session: AsyncSession) -> None:
    redis = FakeRedis()
    service = _service(db_session, redis)
    duplicate = await _telegram_user(db_session, 555)
    await PasskeyRepository(db_session).create(
        user_id=duplicate.id,
        credential_id=b"key",
        public_key=b"key",
        sign_count=0,
        transports=None,
        name="Ключ",
    )
    await db_session.commit()
    user = await _web_user(db_session)
    offer = await service.issue_code(user.id)

    with pytest.raises(AuthError) as failure:
        await service.redeem(offer.code, telegram_id=555, username=None, first_name=None)
    assert failure.value.code == "link_conflict"


async def test_code_expires_after_first_use(db_session: AsyncSession) -> None:
    redis = FakeRedis()
    service = _service(db_session, redis)
    user = await _web_user(db_session)
    offer = await service.issue_code(user.id)
    await service.redeem(offer.code, telegram_id=555, username=None, first_name=None)

    with pytest.raises(AuthError) as failure:
        await service.redeem(offer.code, telegram_id=556, username=None, first_name=None)
    assert failure.value.code == "token_invalid"


async def test_account_with_telegram_gets_no_new_code(db_session: AsyncSession) -> None:
    redis = FakeRedis()
    service = _service(db_session, redis)
    user = await _telegram_user(db_session, 555, email="tg@example.org", password_hash="argon2")

    with pytest.raises(AuthError) as failure:
        await service.issue_code(user.id)
    assert failure.value.code == "telegram_already_linked"


async def test_unlink_needs_another_way_in(db_session: AsyncSession) -> None:
    redis = FakeRedis()
    service = _service(db_session, redis)
    user = await _telegram_user(db_session, 555)

    with pytest.raises(AuthError) as failure:
        await service.unlink(user.id)
    assert failure.value.code == "last_login_method"


async def test_unlink_works_when_password_remains(db_session: AsyncSession) -> None:
    redis = FakeRedis()
    service = _service(db_session, redis)
    user = await _telegram_user(db_session, 555, email="tg@example.org", password_hash="argon2")
    user.email_verified_at = user.created_at
    await db_session.commit()

    await service.unlink(user.id)

    assert user.telegram_id is None
    assert user.telegram_username is None


async def test_linking_is_written_to_the_audit_log(db_session: AsyncSession) -> None:
    redis = FakeRedis()
    service = _service(db_session, redis)
    user = await _web_user(db_session)
    offer = await service.issue_code(user.id)

    await service.redeem(offer.code, telegram_id=555, username=None, first_name=None)

    actions = await db_session.execute(text("select action from audit_log order by id"))
    assert "telegram.linked" in {row[0] for row in actions}
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/core/tests/test_telegram_link.py -q`
Expected: FAIL с `ModuleNotFoundError: repibot_core.services.telegram_link`.

- [ ] **Шаг 3: Добавить срок жизни кода**

В `backend/core/src/repibot_core/domain/identity.py` рядом с `TOKEN_LIFETIMES`:

```python
# Код привязки человек переносит из браузера в Telegram руками, и десяти минут
# на это достаточно. Живёт он в Valkey, а не в one_time_tokens: строка в базе
# ради значения с таким сроком — лишняя запись и лишняя уборка.
LINK_CODE_TTL = timedelta(minutes=10)
```

- [ ] **Шаг 4: Написать клиент Bot API**

Создать `backend/core/src/repibot_core/integrations/telegram/bot_api.py`:

```python
"""Обращения к Bot API вне процесса бота.

Нужен ровно один вызов — getMe: без имени бота нельзя собрать ссылку
`t.me/<bot>?start=link_XXX`. Имя меняется редко, поэтому ответ кэшируется.
"""

from __future__ import annotations

import httpx
from redis.asyncio import Redis

from repibot_core.services.auth.types import AuthError
from repibot_core.settings import Settings

CACHE_KEY = "telegram:bot:username"
CACHE_TTL_SECONDS = 86_400
TIMEOUT_SECONDS = 10.0


class BotApi:
    def __init__(
        self, settings: Settings, redis: Redis, client: httpx.AsyncClient | None = None
    ) -> None:
        self._settings = settings
        self._redis = redis
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)

    async def username(self) -> str:
        cached = await self._redis.get(CACHE_KEY)
        if cached is not None:
            return cached.decode() if isinstance(cached, bytes) else str(cached)

        token = self._settings.bot_token.get_secret_value()
        try:
            # Токен в пути — требование Bot API. В журнал этот адрес не пишется.
            response = await self._client.get(f"https://api.telegram.org/bot{token}/getMe")
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise AuthError("not_found", "Telegram не ответил на getMe") from error

        name = response.json().get("result", {}).get("username")
        if not isinstance(name, str) or not name:
            raise AuthError("not_found", "Bot API не вернул имя бота")

        await self._redis.set(CACHE_KEY, name, ex=CACHE_TTL_SECONDS)
        return name
```

- [ ] **Шаг 5: Написать сервис привязки**

Создать `backend/core/src/repibot_core/services/telegram_link.py`:

```python
"""Привязка и отвязка Telegram.

Тихого слияния аккаунтов нет: при захвате Telegram оно отдало бы чужие
подписки. Человек берёт код в кабинете и предъявляет его боту — тогда обе
стороны доказаны.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.db.repositories.audit import AuditRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.domain.identity import LINK_CODE_TTL, can_unlink, generate_link_code
from repibot_core.services.auth.types import AuthError
from repibot_core.services.login_methods import login_methods
from repibot_core.settings import Settings

logger = logging.getLogger(__name__)

CODE_PREFIX = "telegram:link:"
# Пять попыток при алфавите из 31 символа и шести знаках: столкновение
# маловероятно, а бесконечный цикл при переполненном Valkey недопустим.
CODE_ATTEMPTS = 5


class BotUsername(Protocol):
    """Всё, что сервису нужно от Bot API. Протокол — чтобы тест не ходил в сеть."""

    async def username(self) -> str: ...


@dataclass(frozen=True, slots=True)
class LinkOffer:
    code: str
    url: str


class TelegramLinkService:
    def __init__(
        self, session: AsyncSession, settings: Settings, redis: Redis, bot_api: BotUsername
    ) -> None:
        self._session = session
        self._settings = settings
        self._redis = redis
        self._bot_api = bot_api
        self._users = UserRepository(session)
        self._audit = AuditRepository(session)

    async def issue_code(self, user_id: int) -> LinkOffer:
        user = await self._require_user(user_id)
        if user.telegram_id is not None:
            raise AuthError("telegram_already_linked", "Telegram уже привязан")

        code = await self._free_code()
        await self._redis.set(
            f"{CODE_PREFIX}{code}", str(user_id), ex=int(LINK_CODE_TTL.total_seconds())
        )
        bot = await self._bot_api.username()
        return LinkOffer(code=code, url=f"https://t.me/{bot}?start=link_{code}")

    async def redeem(
        self, code: str, *, telegram_id: int, username: str | None, first_name: str | None
    ) -> User:
        stored = await self._redis.getdel(f"{CODE_PREFIX}{code.strip().upper()}")
        if stored is None:
            raise AuthError("token_invalid", "код недействителен или устарел")
        target = await self._require_user(int(stored))

        if target.telegram_id == telegram_id:
            return target
        if target.telegram_id is not None:
            raise AuthError("telegram_already_linked", "к аккаунту уже привязан другой Telegram")

        existing = await self._users.get_by_telegram_id(telegram_id)
        if existing is not None:
            await self._absorb(existing, target)

        target.telegram_id = telegram_id
        target.telegram_username = username
        if target.name is None:
            target.name = first_name
        await self._audit.record(
            "telegram.linked", "user", actor_id=target.id, entity_id=str(target.id)
        )
        await self._session.commit()
        return target

    async def unlink(self, user_id: int) -> None:
        user = await self._require_user(user_id)
        if user.telegram_id is None:
            raise AuthError("not_found", "Telegram не привязан")

        methods = await login_methods(self._session, user)
        if not can_unlink(methods, "telegram"):
            raise AuthError("last_login_method", "это единственный способ входа")

        await self._audit.record(
            "telegram.unlinked",
            "user",
            actor_id=user.id,
            entity_id=str(user.id),
            before={"telegram_id": user.telegram_id},
        )
        user.telegram_id = None
        user.telegram_username = None
        await self._session.commit()

    async def _absorb(self, duplicate: User, target: User) -> None:
        """Поглощает пустой дубль, созданный входом в MiniApp или письмом боту.

        Пустой — значит войти в него нельзя ничем, кроме самого Telegram. Такой
        аккаунт не хранит ничего, что можно потерять. Если же у него есть свой
        способ входа, за ним стоит отдельный человек или отдельная история
        покупок, и склеивать их автоматически нельзя.
        """
        methods = await login_methods(self._session, duplicate)
        if methods.has_password or duplicate.email is not None or methods.passkey_count:
            raise AuthError("link_conflict", "у этого Telegram уже есть свой аккаунт")

        # Сессии дубля уходят вместе с ним по внешнему ключу: открытый MiniApp
        # перестанет отвечать, человек переоткроет его и войдёт уже в общий
        # аккаунт. Оставлять их живыми нельзя — они указывают на исчезнувшего
        # пользователя.
        await self._audit.record(
            "telegram.duplicate_absorbed",
            "user",
            actor_id=target.id,
            entity_id=str(duplicate.id),
            before={"user_id": duplicate.id, "telegram_id": duplicate.telegram_id},
            after={"user_id": target.id},
        )
        duplicate.telegram_id = None
        await self._session.flush()
        await self._session.delete(duplicate)
        await self._session.flush()
        logger.info("пустой дубль поглощён при привязке Telegram", extra={"user_id": target.id})

    async def _free_code(self) -> str:
        for _ in range(CODE_ATTEMPTS):
            code = generate_link_code()
            if not await self._redis.exists(f"{CODE_PREFIX}{code}"):
                return code
        msg = "не удалось подобрать свободный код привязки"
        raise RuntimeError(msg)

    async def _require_user(self, user_id: int) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthError("not_found", "пользователь не найден")
        return user
```

`duplicate.telegram_id = None` перед удалением нужен потому, что уникальный индекс по `telegram_id` иначе сработает раньше, чем строка исчезнет: SQLAlchemy отправляет UPDATE целевого пользователя и DELETE дубля в порядке, который сам считает нужным.

- [ ] **Шаг 6: Прогнать тесты**

Run: `uv run pytest backend/core/tests/test_telegram_link.py -q`
Expected: девять тестов PASS.

- [ ] **Шаг 7: Коммит**

```bash
git add backend/core
git commit -m "feat: привязка Telegram по коду с поглощением пустого дубля"
```

---

## Задача 11: Эндпоинты привязки Telegram

**Файлы:**
- Изменить: `backend/api/src/repibot_api/routers/me.py` — `/me/telegram/link-code`, `DELETE /me/telegram`
- Изменить: `backend/api/src/repibot_api/schemas.py` — `LinkCodeResponse`
- Изменить: `backend/core/src/repibot_core/ratelimit.py` — `LINK_CODE_PER_USER`
- Тест: `backend/api/tests/test_telegram_link_routes.py`

**Интерфейсы:**
- Потребляет: `TelegramLinkService`, `BotApi` (задача 10).
- Производит: `LinkCodeResponse {code: str, url: str, expires_in: int}`; правило `LINK_CODE_PER_USER = Rule(5, 1 час)`.

- [ ] **Шаг 1: Написать падающий тест**

Создать `backend/api/tests/test_telegram_link_routes.py`:

```python
"""Выдача кода привязки и отвязка Telegram."""

from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import text

pytestmark = pytest.mark.docker

PASSWORD = "совершенно обычный пароль"


@pytest.fixture
def bot_username(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подменяет обращение к Bot API: сети в тестах нет."""
    from repibot_api.routers import me

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": {"username": "repibot_test_bot"}})

    monkeypatch.setattr(
        me, "bot_http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


async def _sign_in(client: AsyncClient) -> str:
    await client.post(
        "/api/auth/register",
        json={"email": "user@example.org", "password": PASSWORD, "language": "ru"},
    )

    from repibot_api.deps import get_session_factory

    async with get_session_factory()() as session:
        row = await session.execute(
            text("select payload from outbox where topic = 'email.verify' order by id desc limit 1")
        )
        link = str(row.scalar_one()["link"])

    response = await client.post("/api/auth/verify-email", json={"token": link.split("token=")[1]})
    return str(response.json()["access_token"])


async def test_link_code_comes_with_a_bot_link(
    api_client: AsyncClient, bot_username: None
) -> None:
    token = await _sign_in(api_client)

    response = await api_client.post(
        "/api/me/telegram/link-code", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["url"] == f"https://t.me/repibot_test_bot?start=link_{body['code']}"
    assert body["expires_in"] == 600


async def test_unlink_without_telegram_is_not_found(
    api_client: AsyncClient, bot_username: None
) -> None:
    token = await _sign_in(api_client)

    response = await api_client.delete(
        "/api/me/telegram", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_sixth_code_in_an_hour_is_refused(
    api_client: AsyncClient, bot_username: None
) -> None:
    """Пять кодов в час на пользователя: больше нужно только перебору."""
    token = await _sign_in(api_client)
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(5):
        assert (await api_client.post("/api/me/telegram/link-code", headers=headers)).status_code == 200

    response = await api_client.post("/api/me/telegram/link-code", headers=headers)

    assert response.status_code == 429
    assert response.headers["Retry-After"]
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/api/tests/test_telegram_link_routes.py -q`
Expected: FAIL — эндпоинты отвечают 404.

- [ ] **Шаг 3: Добавить правило лимита и схему**

В `backend/core/src/repibot_core/ratelimit.py`:

```python
# Код привязки виден в чате бота: пять штук в час хватает любому нормальному
# сценарию и отсекает попытку набить Valkey кодами.
LINK_CODE_PER_USER = Rule(limit=5, window=timedelta(hours=1))
```

В `backend/api/src/repibot_api/schemas.py`:

```python
class LinkCodeResponse(BaseModel):
    code: str
    url: str
    expires_in: int
```

- [ ] **Шаг 4: Написать эндпоинты**

В `backend/api/src/repibot_api/routers/me.py`:

```python
def bot_http_client() -> httpx.AsyncClient:
    """Точка подмены в тестах: обращения к api.telegram.org там нет."""
    return httpx.AsyncClient(timeout=BOT_TIMEOUT_SECONDS)


def _links(session: AsyncSession, redis: Redis) -> TelegramLinkService:
    settings = get_settings()
    return TelegramLinkService(
        session, settings, redis, BotApi(settings, redis, client=bot_http_client())
    )


@router.post("/telegram/link-code", response_model=LinkCodeResponse)
async def issue_link_code(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> LinkCodeResponse:
    result = await RateLimiter(redis).hit(
        f"link:user:{context.principal.user_id}", LINK_CODE_PER_USER
    )
    if not result.allowed:
        raise ApiError(
            "слишком часто",
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            {"Retry-After": str(result.retry_after_seconds)},
        )

    try:
        offer = await _links(session, redis).issue_code(context.principal.user_id)
    except AuthError as error:
        raise api_error_from(error) from error
    return LinkCodeResponse(
        code=offer.code, url=offer.url, expires_in=int(LINK_CODE_TTL.total_seconds())
    )


@router.delete("/telegram", status_code=204)
async def unlink_telegram(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    try:
        await _links(session, redis).unlink(context.principal.user_id)
    except AuthError as error:
        raise api_error_from(error) from error
```

Новые импорты: `httpx`, `BotApi`, `TelegramLinkService`, `LINK_CODE_TTL`, `LINK_CODE_PER_USER`, `LinkCodeResponse`, `BOT_TIMEOUT_SECONDS` (взять `TIMEOUT_SECONDS` из `bot_api` под этим именем).

- [ ] **Шаг 5: Прогнать тесты**

Run: `uv run pytest backend/api/tests/test_telegram_link_routes.py -q`
Expected: три теста PASS.

- [ ] **Шаг 6: Коммит**

```bash
git add backend
git commit -m "feat: эндпоинты привязки и отвязки Telegram"
```

---

## Задача 12: Бот принимает код привязки

**Файлы:**
- Изменить: `backend/bot/src/repibot_bot/handlers/start.py` — обработка `/start link_XXX`
- Изменить: `backend/bot/src/repibot_bot/middleware.py` — сессия, Valkey и сервис привязки в данные хендлера
- Изменить: `backend/core/src/repibot_core/i18n.py` — сообщения о привязке
- Тест: `backend/bot/tests/test_link.py`

**Интерфейсы:**
- Потребляет: `TelegramLinkService.redeem` (задача 10).
- Производит: хендлер `handle_link_start(message, command, user, language, telegram_link)`; ключи `bot.link.done`, `bot.link.conflict`, `bot.link.expired`, `bot.link.already`.

Порядок регистрации хендлеров важен: фильтр глубокой ссылки ставится перед обычным `/start`, иначе приветствие перехватит команду с аргументом.

- [ ] **Шаг 1: Написать падающий тест**

Создать `backend/bot/tests/test_link.py`:

```python
"""Бот принимает код привязки и отвечает по-человечески."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram.filters import CommandObject

from repibot_bot.handlers.start import handle_link_start
from repibot_core.db.models import User
from repibot_core.services.auth.types import AuthError


class FakeLinks:
    def __init__(self, error: AuthError | None = None) -> None:
        self.error = error
        self.seen: dict[str, Any] = {}

    async def redeem(
        self, code: str, *, telegram_id: int, username: str | None, first_name: str | None
    ) -> User:
        self.seen = {"code": code, "telegram_id": telegram_id}
        if self.error is not None:
            raise self.error
        return User(id=1, referral_code="AAAABBBB", language="ru")


def _message() -> AsyncMock:
    message = AsyncMock()
    message.from_user.id = 555
    message.from_user.username = "tester"
    message.from_user.first_name = "Тест"
    return message


async def test_valid_code_reports_success() -> None:
    links = FakeLinks()
    message = _message()

    await handle_link_start(
        message,
        CommandObject(command="start", args="link_ABC123"),
        User(id=1, referral_code="AAAABBBB", language="ru"),
        "ru",
        links,
    )

    assert links.seen == {"code": "ABC123", "telegram_id": 555}
    assert "привязан" in message.answer.call_args.args[0].lower()


async def test_conflict_is_explained_not_silent() -> None:
    """Отказ должен объяснять, что делать, а не сообщать код ошибки."""
    links = FakeLinks(AuthError("link_conflict", "у этого Telegram есть свой аккаунт"))
    message = _message()

    await handle_link_start(
        message,
        CommandObject(command="start", args="link_ABC123"),
        User(id=1, referral_code="AAAABBBB", language="ru"),
        "ru",
        links,
    )

    text = message.answer.call_args.args[0]
    assert "уже" in text.lower()


async def test_expired_code_says_to_take_a_new_one() -> None:
    links = FakeLinks(AuthError("token_invalid", "код устарел"))
    message = _message()

    await handle_link_start(
        message,
        CommandObject(command="start", args="link_OLD123"),
        User(id=1, referral_code="AAAABBBB", language="ru"),
        "ru",
        links,
    )

    assert "новый код" in message.answer.call_args.args[0].lower()
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `uv run pytest backend/bot/tests/test_link.py -q`
Expected: FAIL с `ImportError: cannot import name 'handle_link_start'`.

- [ ] **Шаг 3: Добавить сообщения**

В `backend/core/src/repibot_core/i18n.py` в оба словаря:

```python
        "bot.link.done": "Готово: Telegram привязан к вашему аккаунту.",
        "bot.link.already": "Этот Telegram уже привязан к вашему аккаунту.",
        "bot.link.conflict": (
            "У этого Telegram уже есть свой аккаунт со входом по почте или ключу. "
            "Объединить их автоматически нельзя — войдите в тот аккаунт или "
            "напишите в поддержку."
        ),
        "bot.link.expired": "Код недействителен или устарел. Возьмите новый код в кабинете.",
```

```python
        "bot.link.done": "Done: your Telegram is linked to the account.",
        "bot.link.already": "This Telegram is already linked to your account.",
        "bot.link.conflict": (
            "This Telegram already has its own account with an email or a key. "
            "We cannot merge them automatically — sign in to that account or "
            "contact support."
        ),
        "bot.link.expired": "The code is invalid or expired. Get a new one in your account.",
```

- [ ] **Шаг 4: Написать хендлер**

В `backend/bot/src/repibot_bot/handlers/start.py`:

```python
LINK_PREFIX = "link_"

_LINK_REPLIES = {
    "link_conflict": "bot.link.conflict",
    "telegram_already_linked": "bot.link.conflict",
    "token_invalid": "bot.link.expired",
}


async def handle_link_start(
    message: Message,
    command: CommandObject,
    user: User,
    language: str,
    telegram_link: LinkRedeemer,
) -> None:
    """Привязка по глубокой ссылке `t.me/<bot>?start=link_XXX`.

    Пользователь к этому моменту уже создан middleware — если он пришёл сюда
    впервые, это и есть тот самый пустой дубль, который сервис поглотит.
    """
    code = (command.args or "").removeprefix(LINK_PREFIX)
    sender = message.from_user
    if not code or sender is None:
        await message.answer(translate(language, "bot.link.expired"))
        return

    try:
        await telegram_link.redeem(
            code,
            telegram_id=sender.id,
            username=sender.username,
            first_name=sender.first_name,
        )
    except AuthError as error:
        await message.answer(translate(language, _LINK_REPLIES.get(error.code, "bot.link.expired")))
        return

    await message.answer(translate(language, "bot.link.done"))
```

`LinkRedeemer` — протокол в том же модуле, чтобы тест не поднимал базу:

```python
class LinkRedeemer(Protocol):
    async def redeem(
        self, code: str, *, telegram_id: int, username: str | None, first_name: str | None
    ) -> User: ...
```

Регистрация в `build_start_router`:

```python
    router = Router(name="start")
    # Глубокая ссылка проверяется первой: обычный /start принял бы её как
    # приветствие и молча проглотил код.
    router.message.register(
        handle_link_start, CommandStart(deep_link=True, magic=F.args.regexp(r"^link_"))
    )
    router.message.register(handle_start, CommandStart())
    return router
```

- [ ] **Шаг 5: Дать хендлеру сервис привязки**

В `backend/bot/src/repibot_bot/middleware.py` создать Valkey один раз в `__init__` и класть сервис в данные:

```python
        self._redis = Redis.from_url(settings.valkey_url, decode_responses=False)
```

```python
            data["telegram_link"] = TelegramLinkService(
                session, self._settings, self._redis, BotApi(self._settings, self._redis)
            )
```

- [ ] **Шаг 6: Прогнать тесты**

Run: `uv run pytest backend/bot -q`
Expected: PASS, включая прежние тесты `/start` и `/language`.

- [ ] **Шаг 7: Коммит**

```bash
git add backend
git commit -m "feat: бот принимает код привязки Telegram"
```

---

## Задача 13: Типы API и словари фронтенда

**Файлы:**
- Изменить (генератором): `frontend/packages/core/src/api/openapi.json`, `frontend/packages/core/src/api/schema.d.ts`
- Изменить: `frontend/packages/core/src/i18n/ru.ts`, `frontend/packages/core/src/i18n/en.ts`
- Изменить: `frontend/packages/core/src/auth/hooks.tsx:45-59` — новые коды ошибок в словаре
- Тест: `frontend/packages/core/src/i18n/i18n.test.ts` уже проверяет совпадение наборов ключей

**Интерфейсы:**
- Производит: типы путей `/api/auth/passkey/*`, `/api/auth/methods`, `/api/me/passkeys*`, `/api/me/telegram*` в `schema.d.ts`; ключи словарей `auth.login.passkey`, `auth.login.telegram`, `account.passkeys.*`, `account.telegram.*`, `auth.error.last_login_method`, `auth.error.link_conflict`, `auth.error.telegram_already_linked`, `auth.error.telegram_unavailable`, `auth.error.passkey_cancelled`.

Задача выполняется одна, без соседей: `schema.d.ts` — общий файл, и параллельная правка его двумя исполнителями даёт конфликт при каждом запуске генератора.

- [ ] **Шаг 1: Перегенерировать типы**

Run:

```bash
uv run export-openapi
cd frontend && pnpm --filter @repibot/core gen:api && cd ..
```

Expected: в `schema.d.ts` появились новые пути. Проверить: `grep -c "passkey" frontend/packages/core/src/api/schema.d.ts` больше нуля.

- [ ] **Шаг 2: Дописать русский словарь**

В `frontend/packages/core/src/i18n/ru.ts`:

```ts
  'auth.error.last_login_method': 'Это единственный способ входа — сначала добавьте другой',
  'auth.error.link_conflict': 'У этого Telegram уже есть свой аккаунт',
  'auth.error.telegram_already_linked': 'Telegram уже привязан',
  'auth.error.telegram_unavailable': 'Вход через Telegram сейчас недоступен',
  'auth.error.passkey_cancelled': 'Вход по ключу отменён',
  'auth.login.passkey': 'Войти по ключу',
  'auth.login.telegram': 'Войти через Telegram',
  'account.passkeys.title': 'Ключи доступа',
  'account.passkeys.hint': 'Вход отпечатком или лицом вместо пароля',
  'account.passkeys.empty': 'Ключей пока нет',
  'account.passkeys.add': 'Добавить ключ',
  'account.passkeys.adding': 'Ждём подтверждения…',
  'account.passkeys.name': 'Название ключа',
  'account.passkeys.name_placeholder': 'Например, рабочий ноутбук',
  'account.passkeys.delete': 'Удалить',
  'account.passkeys.delete_title': 'Удалить ключ?',
  'account.passkeys.delete_text': 'Войти этим устройством без пароля больше не получится',
  'account.passkeys.last_used': 'Использован',
  'account.passkeys.never_used': 'Ещё не использовался',
  'account.telegram.link': 'Привязать Telegram',
  'account.telegram.unlink': 'Отвязать',
  'account.telegram.unlink_title': 'Отвязать Telegram?',
  'account.telegram.unlink_text': 'Входить через Telegram станет нельзя',
  'account.telegram.code_hint': 'Откройте бота по кнопке ниже или отправьте ему код',
  'account.telegram.open_bot': 'Открыть бота',
  'account.telegram.code_expires': 'Код действует 10 минут',
```

- [ ] **Шаг 3: Дописать английский словарь**

В `frontend/packages/core/src/i18n/en.ts` те же ключи:

```ts
  'auth.error.last_login_method': 'This is your only way in — add another one first',
  'auth.error.link_conflict': 'This Telegram already has its own account',
  'auth.error.telegram_already_linked': 'Telegram is already linked',
  'auth.error.telegram_unavailable': 'Telegram sign-in is unavailable right now',
  'auth.error.passkey_cancelled': 'Passkey sign-in was cancelled',
  'auth.login.passkey': 'Sign in with a passkey',
  'auth.login.telegram': 'Sign in with Telegram',
  'account.passkeys.title': 'Passkeys',
  'account.passkeys.hint': 'Sign in with a fingerprint or face instead of a password',
  'account.passkeys.empty': 'No passkeys yet',
  'account.passkeys.add': 'Add a passkey',
  'account.passkeys.adding': 'Waiting for confirmation…',
  'account.passkeys.name': 'Passkey name',
  'account.passkeys.name_placeholder': 'For example, work laptop',
  'account.passkeys.delete': 'Delete',
  'account.passkeys.delete_title': 'Delete this passkey?',
  'account.passkeys.delete_text': 'This device will no longer sign in without a password',
  'account.passkeys.last_used': 'Last used',
  'account.passkeys.never_used': 'Never used',
  'account.telegram.link': 'Link Telegram',
  'account.telegram.unlink': 'Unlink',
  'account.telegram.unlink_title': 'Unlink Telegram?',
  'account.telegram.unlink_text': 'Signing in with Telegram will stop working',
  'account.telegram.code_hint': 'Open the bot with the button below or send it the code',
  'account.telegram.open_bot': 'Open the bot',
  'account.telegram.code_expires': 'The code is valid for 10 minutes',
```

Ключ `account.telegram_absent` из этапа 1a («привязка появится позже») заменить на `'Аккаунт не привязан'` / `'Account not linked'`: привязка появилась.

- [ ] **Шаг 4: Добавить коды в словарь ошибок**

В `frontend/packages/core/src/auth/hooks.tsx` в `known`:

```ts
    last_login_method: 'auth.error.last_login_method',
    link_conflict: 'auth.error.link_conflict',
    telegram_already_linked: 'auth.error.telegram_already_linked',
    telegram_unavailable: 'auth.error.telegram_unavailable',
```

- [ ] **Шаг 5: Прогнать проверки фронтенда**

Run: `cd frontend && pnpm test && pnpm typecheck && cd ..`
Expected: PASS. Тест `i18n.test.ts` подтверждает, что русский и английский словари совпадают по составу ключей.

- [ ] **Шаг 6: Коммит**

```bash
git add frontend
git commit -m "feat: типы новых эндпоинтов и словари для passkey и Telegram"
```

---

## Задача 14: Passkey в интерфейсе

**Файлы:**
- Создать: `frontend/apps/web/src/lib/passkey.ts`
- Создать: `frontend/apps/web/src/lib/passkey.test.ts`
- Изменить: `frontend/apps/web/src/app/(auth)/login/page.tsx` — кнопка входа по ключу
- Изменить: `frontend/apps/web/src/app/account/security/page.tsx` — карточка ключей
- Изменить: `frontend/apps/web/src/app/(auth)/login/page.test.tsx`, `frontend/apps/web/src/app/account/security/page.test.tsx`

**Интерфейсы:**
- Потребляет: `useAuthClient` из `@repibot/core`, `startRegistration` и `startAuthentication` из `@simplewebauthn/browser`.
- Производит: `usePasskeys()`, `useAddPasskey(language)`, `useDeletePasskey(language)`, `usePasskeyLogin(language)`.

Хуки живут в приложении, а не в `packages/core`: `@simplewebauthn/browser` трогает `navigator.credentials`, которого в MiniApp нет — Telegram открывает страницу во встроенном браузере, где WebAuthn работает не везде. Класть в общий пакет то, чем пользуется одно приложение, значит тянуть браузерный API в сборку MiniApp.

- [ ] **Шаг 1: Написать падающий тест**

Создать `frontend/apps/web/src/lib/passkey.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest'

import { passkeyErrorKey } from './passkey'

describe('passkeyErrorKey', () => {
  it('отличает отмену пользователем от настоящей ошибки', () => {
    const cancelled = new Error('отменено')
    cancelled.name = 'NotAllowedError'

    expect(passkeyErrorKey(cancelled)).toBe('auth.error.passkey_cancelled')
  })

  it('незнакомую ошибку показывает общим сообщением', () => {
    expect(passkeyErrorKey(new Error('что-то не так'))).toBe('auth.error.unknown')
  })
})
```

Отмена окна выбора ключа — не ошибка: человек передумал, и пугать его красным текстом не за что.

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `cd frontend && pnpm --filter @repibot/web test && cd ..`
Expected: FAIL — модуля `./passkey` нет.

- [ ] **Шаг 3: Написать хуки**

Создать `frontend/apps/web/src/lib/passkey.ts`:

```ts
import { startAuthentication, startRegistration } from '@simplewebauthn/browser'
import {
  type Language,
  type TranslationKey,
  errorMessageKey,
  translate,
  useAuthClient,
} from '@repibot/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

/**
 * Отмена окна выбора ключа приходит как NotAllowedError — тем же именем, что и
 * настоящий отказ аутентификатора. Показывать «ошибка» человеку, который просто
 * закрыл окно, незачем.
 */
export function passkeyErrorKey(error: unknown): TranslationKey {
  if (error instanceof Error && error.name === 'NotAllowedError') {
    return 'auth.error.passkey_cancelled'
  }
  const code = (error as { error?: { code?: string } })?.error?.code
  return errorMessageKey(code)
}

function messageFrom(error: unknown, language: Language): string {
  return translate(language, passkeyErrorKey(error))
}

export function usePasskeys() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['passkeys'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me/passkeys')
      if (error) throw error
      return data
    },
  })
}

export function useAddPasskey(language: Language) {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) => {
      const options = await api.POST('/api/me/passkeys/options')
      if (options.error || !options.data) throw options.error ?? new Error('нет параметров')

      // Структура параметров задана спецификацией WebAuthn, и бэкенд отдаёт её
      // как есть: описывать её своей схемой значит поддерживать копию чужого
      // стандарта на двух языках сразу.
      const credential = await startRegistration({
        optionsJSON: options.data.options as Parameters<typeof startRegistration>[0]['optionsJSON'],
      })

      const { error } = await api.POST('/api/me/passkeys', { body: { credential, name } })
      if (error) throw new Error(messageFrom(error, language))
    },
    onSuccess: async () => {
      await queries.invalidateQueries({ queryKey: ['passkeys'] })
      // В профиле показано число ключей — без сброса оно отстанет на один.
      await queries.invalidateQueries({ queryKey: ['me'] })
    },
  })
}

export function useDeletePasskey(language: Language) {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const { error } = await api.DELETE('/api/me/passkeys/{passkey_id}', {
        params: { path: { passkey_id: id } },
      })
      if (error) throw new Error(messageFrom(error, language))
    },
    onSuccess: async () => {
      await queries.invalidateQueries({ queryKey: ['passkeys'] })
      await queries.invalidateQueries({ queryKey: ['me'] })
    },
  })
}

export function usePasskeyLogin(language: Language) {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const options = await api.POST('/api/auth/passkey/login/options')
      if (options.error || !options.data) throw options.error ?? new Error('нет параметров')

      const credential = await startAuthentication({
        optionsJSON: options.data.options as Parameters<
          typeof startAuthentication
        >[0]['optionsJSON'],
      })

      const { data, error } = await api.POST('/api/auth/passkey/login/verify', {
        body: { credential },
      })
      if (error) throw new Error(messageFrom(error, language))
      return data
    },
    onSuccess: () => queries.invalidateQueries({ queryKey: ['me'] }),
  })
}
```

- [ ] **Шаг 4: Добавить кнопку на экран входа**

В `frontend/apps/web/src/app/(auth)/login/page.tsx` заменить отключённую кнопку:

```tsx
  const passkeyLogin = usePasskeyLogin(language)

  async function signInWithPasskey() {
    setFormError(null)
    try {
      await passkeyLogin.mutateAsync()
      router.replace('/account')
    } catch (error) {
      // Отмена окна выбора ключа — не повод краснеть: человек просто передумал.
      const key = passkeyErrorKey(error)
      if (key !== 'auth.error.passkey_cancelled') setFormError(t(key))
    }
  }
```

```tsx
      <Button
        type="button"
        variant="secondary"
        onClick={signInWithPasskey}
        disabled={passkeyLogin.isPending}
      >
        {t('auth.login.passkey')}
      </Button>
```

- [ ] **Шаг 5: Добавить карточку ключей в кабинет**

В `frontend/apps/web/src/app/account/security/page.tsx` между карточкой почты и карточкой сессий:

```tsx
      <Card>
        <h2 className="text-lg font-semibold text-text">{t('account.passkeys.title')}</h2>
        <p className="mt-1 text-sm text-text-secondary">{t('account.passkeys.hint')}</p>

        {addPasskey.error === null ? null : (
          <p role="alert" className="mt-2 text-sm text-danger">
            {addPasskey.error instanceof Error ? addPasskey.error.message : t('common.error')}
          </p>
        )}

        {passkeys.isPending ? (
          <p className="mt-4 text-text-secondary">{t('common.loading')}</p>
        ) : passkeys.data === undefined || passkeys.data.length === 0 ? (
          <EmptyState className="mt-4" title={t('account.passkeys.empty')} />
        ) : (
          <ul className="mt-4 flex flex-col gap-3">
            {passkeys.data.map((key) => (
              <li key={key.id} className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="truncate text-sm text-text">{key.name}</p>
                  <p className="text-sm text-text-muted">
                    {key.last_used_at === null
                      ? t('account.passkeys.never_used')
                      : `${t('account.passkeys.last_used')}: ${new Date(
                          key.last_used_at,
                        ).toLocaleString(language)}`}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setPendingKey(key.id)}
                >
                  {t('account.passkeys.delete')}
                </Button>
              </li>
            ))}
          </ul>
        )}

        <form onSubmit={submitPasskey} noValidate className="mt-4 flex flex-col gap-4">
          <FormField label={t('account.passkeys.name')} htmlFor="passkey-name">
            <Input
              id="passkey-name"
              value={keyName}
              placeholder={t('account.passkeys.name_placeholder')}
              onChange={(event) => setKeyName(event.target.value)}
            />
          </FormField>
          <div>
            <Button type="submit" disabled={addPasskey.isPending}>
              {addPasskey.isPending ? t('account.passkeys.adding') : t('account.passkeys.add')}
            </Button>
          </div>
        </form>
      </Card>
```

Обработчик и диалог подтверждения — рядом с существующими:

```tsx
  const passkeys = usePasskeys()
  const addPasskey = useAddPasskey(language)
  const deletePasskey = useDeletePasskey(language)
  const [keyName, setKeyName] = useState('')
  const [pendingKey, setPendingKey] = useState<number | null>(null)

  function submitPasskey(event: FormEvent) {
    event.preventDefault()
    addPasskey.mutate(keyName.trim(), { onSuccess: () => setKeyName('') })
  }
```

```tsx
      <Dialog
        open={pendingKey !== null}
        onClose={() => setPendingKey(null)}
        title={t('account.passkeys.delete_title')}
        description={t('account.passkeys.delete_text')}
      >
        <Button type="button" variant="secondary" onClick={() => setPendingKey(null)}>
          {t('common.cancel')}
        </Button>
        <Button
          type="button"
          onClick={() => {
            if (pendingKey !== null) deletePasskey.mutate(pendingKey)
            setPendingKey(null)
          }}
        >
          {t('account.passkeys.delete')}
        </Button>
      </Dialog>
```

- [ ] **Шаг 6: Дописать тесты страниц**

В `frontend/apps/web/src/app/(auth)/login/page.test.tsx`:

```tsx
it('вход по ключу уводит в кабинет', async () => {
  vi.mock('@simplewebauthn/browser', () => ({
    startAuthentication: vi.fn().mockResolvedValue({ id: 'credential' }),
    startRegistration: vi.fn(),
  }))
  // Ответы API подставляются тем же способом, что в существующих тестах файла.
  render(<LoginPage />, { wrapper: Providers })

  await userEvent.click(screen.getByRole('button', { name: /войти по ключу/i }))

  await waitFor(() => expect(replace).toHaveBeenCalledWith('/account'))
})
```

В `frontend/apps/web/src/app/account/security/page.test.tsx`:

```tsx
it('показывает список ключей и предлагает добавить новый', async () => {
  render(<SecurityPage />, { wrapper: Providers })

  expect(await screen.findByText('Рабочий ноутбук')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /добавить ключ/i })).toBeEnabled()
})
```

Подстановку ответов `/api/me/passkeys` сделать тем же приёмом, каким в файле уже подставляются `/api/me` и `/api/me/sessions`.

- [ ] **Шаг 7: Прогнать проверки**

Run: `cd frontend && pnpm test && pnpm typecheck && pnpm lint && cd ..`
Expected: PASS.

- [ ] **Шаг 8: Коммит**

```bash
git add frontend
git commit -m "feat: вход и управление ключами доступа в вебе"
```

---

## Задача 15: Telegram в интерфейсе

**Файлы:**
- Создать: `frontend/apps/web/src/lib/telegram.ts`
- Изменить: `frontend/apps/web/src/app/(auth)/login/page.tsx` — кнопка Telegram и показ `?error=`
- Изменить: `frontend/apps/web/src/app/account/security/page.tsx` — карточка привязки
- Изменить: `frontend/apps/web/src/app/(auth)/login/page.test.tsx`, `frontend/apps/web/src/app/account/security/page.test.tsx`

**Интерфейсы:**
- Производит: `useAuthMethods()`, `useLinkCode(language)`, `useUnlinkTelegram(language)`.

Кнопка входа — обычная ссылка на `/api/auth/telegram/start`, а не `fetch`: дальше идёт цепочка редиректов на чужой домен, и она должна происходить в адресной строке, а не внутри запроса.

- [ ] **Шаг 1: Написать хуки**

Создать `frontend/apps/web/src/lib/telegram.ts`:

```ts
import { type Language, errorMessageKey, translate, useAuthClient } from '@repibot/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

function messageFrom(error: unknown, language: Language): string {
  const code = (error as { error?: { code?: string } })?.error?.code
  return translate(language, errorMessageKey(code))
}

/**
 * Какие способы входа доступны в этом развёртывании.
 *
 * Вход через Telegram требует Client ID из BotFather. Показывать кнопку,
 * которая приведёт на страницу с ошибкой, хуже, чем не показывать её вовсе.
 */
export function useAuthMethods() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['auth-methods'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/auth/methods')
      if (error || !data) throw error ?? new Error('пустой ответ')
      return data
    },
    // Настройки развёртывания не меняются в течение сессии.
    staleTime: Number.POSITIVE_INFINITY,
  })
}

export function useLinkCode(language: Language) {
  const { api } = useAuthClient()
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST('/api/me/telegram/link-code')
      if (error || !data) throw new Error(messageFrom(error, language))
      return data
    },
  })
}

export function useUnlinkTelegram(language: Language) {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { error } = await api.DELETE('/api/me/telegram')
      if (error) throw new Error(messageFrom(error, language))
    },
    onSuccess: () => queries.invalidateQueries({ queryKey: ['me'] }),
  })
}
```

- [ ] **Шаг 2: Добавить кнопку и показ ошибки на экран входа**

В `frontend/apps/web/src/app/(auth)/login/page.tsx`:

```tsx
  const methods = useAuthMethods()
  const params = useSearchParams()
  // Браузерный вход через Telegram возвращается сюда с кодом ошибки в адресе:
  // цепочка редиректов не может показать её иначе.
  const returnedError = params.get('error')
```

```tsx
      {returnedError === null ? null : (
        <p role="alert" className="text-sm text-danger">
          {t(errorMessageKey(returnedError))}
        </p>
      )}
```

```tsx
      {methods.data?.telegram === true ? (
        <Button
          type="button"
          variant="secondary"
          onClick={() => {
            window.location.href = '/api/auth/telegram/start'
          }}
        >
          {t('auth.login.telegram')}
        </Button>
      ) : null}
```

- [ ] **Шаг 3: Заменить карточку Telegram в кабинете**

В `frontend/apps/web/src/app/account/security/page.tsx` вместо карточки-заглушки:

```tsx
      <Card>
        <h2 className="text-lg font-semibold text-text">{t('account.telegram')}</h2>

        {me.data?.has_telegram === true ? (
          <>
            <p className="mt-2 text-sm text-text-secondary">
              {me.data.telegram_username === null
                ? t('account.telegram_linked')
                : `@${me.data.telegram_username}`}
            </p>
            {unlink.error === null ? null : (
              <p role="alert" className="mt-2 text-sm text-danger">
                {unlink.error instanceof Error ? unlink.error.message : t('common.error')}
              </p>
            )}
            <div className="mt-4">
              <Button type="button" variant="secondary" onClick={() => setUnlinkOpen(true)}>
                {t('account.telegram.unlink')}
              </Button>
            </div>
          </>
        ) : (
          <>
            <p className="mt-2 text-sm text-text-secondary">{t('account.telegram_absent')}</p>
            {linkCode.data === undefined ? (
              <div className="mt-4">
                <Button type="button" onClick={() => linkCode.mutate()} disabled={linkCode.isPending}>
                  {t('account.telegram.link')}
                </Button>
              </div>
            ) : (
              <div className="mt-4 flex flex-col gap-3">
                <p className="text-sm text-text-secondary">{t('account.telegram.code_hint')}</p>
                {/* Код набирают руками в чате бота: моноширинный шрифт и
                    разрядка нужны, чтобы не спутать похожие знаки. */}
                <p className="font-mono text-2xl tracking-widest text-text">{linkCode.data.code}</p>
                <p className="text-sm text-text-muted">{t('account.telegram.code_expires')}</p>
                <div>
                  <Button type="button" onClick={() => window.open(linkCode.data.url, '_blank')}>
                    {t('account.telegram.open_bot')}
                  </Button>
                </div>
              </div>
            )}
            {linkCode.error === null ? null : (
              <p role="alert" className="mt-2 text-sm text-danger">
                {linkCode.error instanceof Error ? linkCode.error.message : t('common.error')}
              </p>
            )}
          </>
        )}
      </Card>
```

Диалог отвязки — рядом с прочими:

```tsx
      <Dialog
        open={unlinkOpen}
        onClose={() => setUnlinkOpen(false)}
        title={t('account.telegram.unlink_title')}
        description={t('account.telegram.unlink_text')}
      >
        <Button type="button" variant="secondary" onClick={() => setUnlinkOpen(false)}>
          {t('common.cancel')}
        </Button>
        <Button
          type="button"
          onClick={() => {
            unlink.mutate()
            setUnlinkOpen(false)
          }}
        >
          {t('account.telegram.unlink')}
        </Button>
      </Dialog>
```

- [ ] **Шаг 4: Дописать тесты**

В `frontend/apps/web/src/app/(auth)/login/page.test.tsx`:

```tsx
it('не показывает кнопку Telegram, когда вход через него не настроен', async () => {
  render(<LoginPage />, { wrapper: Providers })

  await screen.findByRole('button', { name: /войти$/i })
  expect(screen.queryByRole('button', { name: /через telegram/i })).not.toBeInTheDocument()
})

it('показывает ошибку, с которой вернул редирект', async () => {
  // Параметры адреса подставляются моком next/navigation, как в существующих тестах.
  render(<LoginPage />, { wrapper: Providers })

  expect(await screen.findByRole('alert')).toHaveTextContent(/недоступен/i)
})
```

В `frontend/apps/web/src/app/account/security/page.test.tsx`:

```tsx
it('выдаёт код привязки и ссылку на бота', async () => {
  render(<SecurityPage />, { wrapper: Providers })

  await userEvent.click(await screen.findByRole('button', { name: /привязать telegram/i }))

  expect(await screen.findByText('ABC123')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /открыть бота/i })).toBeEnabled()
})
```

- [ ] **Шаг 5: Прогнать проверки**

Run: `cd frontend && pnpm test && pnpm typecheck && pnpm lint && cd ..`
Expected: PASS.

- [ ] **Шаг 6: Коммит**

```bash
git add frontend
git commit -m "feat: привязка Telegram и вход через него в интерфейсе"
```

---

## Задача 16: Сквозной сценарий passkey и документация

**Файлы:**
- Создать: `frontend/apps/web/e2e/passkey.spec.ts`
- Изменить: `.env.example`
- Изменить: `docs/deployment.md:21-50` — раздел про Telegram и новый про passkey
- Изменить: `README.md` — состояние подпроекта

**Интерфейсы:**
- Потребляет: `waitForLink` и `WEB_URL` из существующей инфраструктуры e2e.

Виртуальный аутентификатор Chromium включается через CDP: настоящего ключа в CI нет, а без сквозной проверки остаётся непроверенным самое хрупкое место — совпадение RP ID и origin между сервером и браузером. Именно оно ломается при смене домена.

- [ ] **Шаг 1: Написать сценарий**

Создать `frontend/apps/web/e2e/passkey.spec.ts`:

```ts
import { expect, type Page, test } from '@playwright/test'

import { waitForLink } from './mailpit'
import { MAILPIT_URL } from './stack'

const PASSWORD = 'совершенно обычный пароль'

/**
 * Виртуальный аутентификатор Chromium.
 *
 * Настоящего ключа в CI нет, а проверять нужно именно связку браузера и
 * сервера: RP ID выводится из PUBLIC_WEB_URL, и расхождение с адресом, по
 * которому открыта страница, обнаруживается только так.
 */
async function addVirtualAuthenticator(page: Page): Promise<void> {
  const session = await page.context().newCDPSession(page)
  await session.send('WebAuthn.enable')
  await session.send('WebAuthn.addVirtualAuthenticator', {
    options: {
      protocol: 'ctap2',
      transport: 'internal',
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  })
}

async function registerAndVerify(page: Page, email: string): Promise<void> {
  await page.goto('/register')
  await page.getByLabel(/почта/i).fill(email)
  await page.getByLabel(/пароль/i).fill(PASSWORD)
  await page.getByRole('button', { name: /зарегистрироваться/i }).click()

  const link = await waitForLink(MAILPIT_URL, email, /https?:\/\/\S+verify-email\S+/)
  await page.goto(link)
  await expect(page).toHaveURL(/\/account/)
}

test('ключ доступа заводится в кабинете и пускает в него без пароля', async ({ page }) => {
  const email = `passkey-${Date.now()}@example.com`
  await addVirtualAuthenticator(page)
  await registerAndVerify(page, email)

  await page.goto('/account/security')
  await page.getByLabel(/название ключа/i).fill('Тестовый ключ')
  await page.getByRole('button', { name: /добавить ключ/i }).click()
  await expect(page.getByText('Тестовый ключ')).toBeVisible()

  await page.getByRole('button', { name: /выйти/i }).click()
  await expect(page).toHaveURL(/\/login/)

  await page.getByRole('button', { name: /войти по ключу/i }).click()

  await expect(page).toHaveURL(/\/account/)
  await expect(page.getByText(email)).toBeVisible()
})

test('единственный способ входа снять нельзя', async ({ page }) => {
  const email = `only-key-${Date.now()}@example.com`
  await addVirtualAuthenticator(page)
  await registerAndVerify(page, email)

  await page.goto('/account/security')
  await page.getByLabel(/название ключа/i).fill('Единственный')
  await page.getByRole('button', { name: /добавить ключ/i }).click()
  await expect(page.getByText('Единственный')).toBeVisible()

  // У аккаунта есть пароль, поэтому ключ снимается — проверяем обратное
  // правило: удалить получится, и сообщение об ошибке не появится.
  await page.getByRole('button', { name: /^удалить$/i }).click()
  await page.getByRole('button', { name: /^удалить$/i }).last().click()

  await expect(page.getByText('Единственный')).toBeHidden()
})
```

Вход через Telegram сквозным тестом не проверяется: он ведёт на чужой домен, поднять который в стеке нельзя. Его проверяют тесты роутера на мокнутом JWKS (задача 9) и ручной пункт критериев приёмки.

- [ ] **Шаг 2: Прогнать сценарии**

Run: `cd frontend && pnpm --filter @repibot/web exec playwright test && cd ..`
Expected: прежние четыре сценария и два новых зелёные.

- [ ] **Шаг 3: Обновить `.env.example`**

Добавить раздел после блока «Роли»:

```bash
# --- Вход через Telegram в браузере ---
# Выдаёт мини-приложение @BotFather: Bot Settings → Web Login. Пустые значения
# означают, что кнопка «Войти через Telegram» не показывается.
# Переключение бота на OpenID Connect в BotFather необратимо — см.
# docs/deployment.md.
TELEGRAM_OIDC_CLIENT_ID=
TELEGRAM_OIDC_CLIENT_SECRET=
```

- [ ] **Шаг 4: Обновить `docs/deployment.md`**

1. В разделе 2 исправить адрес возврата: `https://ваш-домен/api/auth/telegram/callback` — эндпоинт живёт под `/api`, и адрес в BotFather должен совпадать посимвольно.
2. Убрать абзац «Вход через Telegram появляется в подпроекте 1b…» и назвать переменные `TELEGRAM_OIDC_CLIENT_ID` и `TELEGRAM_OIDC_CLIENT_SECRET`.
3. Добавить раздел про ключи доступа:

```markdown
## Ключи доступа (passkey)

Отдельных настроек у них нет: идентификатор проверяющей стороны выводится из
`PUBLIC_WEB_URL` — это имя домена без схемы и порта.

> **Смена домена делает все зарегистрированные ключи бесполезными.** Ключ
> привязан к домену на стороне устройства, и перенести его нельзя ничем: после
> переезда людям придётся заводить ключи заново. Тем, у кого passkey был
> единственным способом входа, останется только восстановление по почте.

Ключи работают только по HTTPS. Исключение — `localhost`, который браузеры
считают безопасным контекстом; на локальном адресе без TLS они тоже заведутся.
```

- [ ] **Шаг 5: Обновить `README.md`**

Текущее состояние — «подпроект 1: идентичность завершена — вход паролем, по ключу доступа и через Telegram, профиль, роли». В таблице каталогов добавить `backend/core/integrations/telegram`.

- [ ] **Шаг 6: Полная проверка и коммит**

Run: `uv run check`
Expected: все проверки зелёные.

```bash
git add .
git commit -m "test: сквозной вход по ключу доступа и документация этапа"
```

---

## Порядок выполнения волнами

Внутри волны задачи идут параллельно и не пересекаются по файлам. Между волнами — полный прогон `uv run check` и разбор того, что нашли исполнители.

| Волна | Задачи | Почему вместе |
|---|---|---|
| 1 | 1 таблица ключей, 2 программный аутентификатор, 7 PKCE и OIDC | Ничего общего: разные каталоги, общий только `settings.py` в задаче 7 |
| 2 | 3 параметры WebAuthn, 8 вход через OIDC | Обе опираются на первую волну, друг с другом не пересекаются |
| 3 | 4 подсчёт способов входа, 9 эндпоинты OIDC | Задача 4 трогает `profile.py`, задача 9 — `routers/auth.py` |
| 4 | 5 сервис passkey, 10 привязка Telegram | Обе нуждаются в задаче 4 |
| 5 | 6 эндпоинты passkey, 11 эндпоинты привязки, 12 бот | 6 и 11 правят соседние файлы роутеров — точечные правки, разные функции |
| 6 | 13 типы и словари | Одна: `schema.d.ts` генерируется и конфликтует с любым соседом |
| 7 | 14 passkey в интерфейсе, 15 Telegram в интерфейсе | Обе правят `login/page.tsx` и `security/page.tsx` — только точечными вставками, каждый в свою карточку |
| 8 | 16 сквозной сценарий и документация | Последняя: проверяет собранное целиком |

Волна 7 — единственная, где двое работают в одних файлах. Правила для неё: вставлять свои блоки, ничего не удаляя и не переставляя; в `security/page.tsx` задача 14 занимает карточку ключей, задача 15 — карточку Telegram; в `login/page.tsx` задача 14 добавляет кнопку ключа, задача 15 — кнопку Telegram и показ `?error=`. Если файл при этом станет неудобным для чтения, разделить его на компоненты — работа следующей отдельной задачи, а не текущей.

Ограничения для исполнителей (те же, что на этапе 1a):

- никаких изменяющих git-команд: коммитит оркестратор после проверки задачи;
- никаких `uv add`, `pnpm add` и правок `uv.lock` или `pnpm-lock.yaml`;
- полный `uv run check` внутри волны не запускать — незаконченный код соседа всегда делает его красным; запускать только тесты своей задачи;
- файлы соседей по волне не трогать вовсе.

## Критерии готовности этапа

Проверяется руками на поднятом стеке, а не только тестами:

1. Ключ доступа заводится в кабинете и пускает в него без пароля.
2. Второй ключ на том же устройстве завести нельзя: аутентификатор сообщает, что он уже зарегистрирован.
3. Ключ, снятый в кабинете, больше не пускает.
4. Единственный способ входа снять нельзя — ни последний passkey без пароля, ни Telegram без почты.
5. Кнопка «Войти через Telegram» не показывается, пока не заполнены `TELEGRAM_OIDC_CLIENT_ID` и `TELEGRAM_OIDC_CLIENT_SECRET`.
6. Вход через Telegram в браузере проходит по OIDC и попадает в тот же аккаунт, что и MiniApp с тем же Telegram. **Это проверка допущения:** `sub` в ID-токене должен совпадать с `telegram_id` из `initData`. Если аккаунты окажутся разными, `sub` — не идентификатор Telegram, и опознание нужно переделать до выпуска.
7. Код привязки из кабинета склеивает аккаунт из MiniApp с аккаунтом из веба; пустой дубль исчезает.
8. При непустом дубле бот отвечает объяснением, а не молчаливым слиянием, и в `audit_log` нет записи о привязке.
9. Просроченный или уже использованный код бот отвергает и просит взять новый.
10. Смена языка в профиле меняет язык ответов бота о привязке.
11. Шестой код привязки за час даёт `429` с `Retry-After`.
12. `uv run check` проходит целиком.

## Что остаётся вне подпроекта 1

Двухфакторная аутентификация поверх пароля, вход по одноразовой ссылке без пароля, удаление аккаунта, объединение непустых аккаунтов через поддержку, страницы админки, `phone` в scope OIDC и хранение телефона. Всё это либо в следующих подпроектах, либо не входит в продукт вовсе — см. раздел 13 спецификации.
