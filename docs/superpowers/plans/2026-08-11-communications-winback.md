# Лесенка возврата Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ушедший пользователь получает четыре касания — напоминание, личный
промокод, бесплатные дни в одну кнопку и последнее письмо, — и не может
получить их снова раньше чем через полгода.

**Architecture:** Крон `run_winback` раз в сутки берёт подписки, истёкшие
ровно столько дней назад, сколько указано в настройке, и ставит очередную
ступень через `NotificationService.enqueue` с категорией `marketing`. Ступени
с подарком фиксируются в `winback_grants`; ключом служит `telegram_id`, если
Telegram привязан, иначе `user_id` — та же защита, что у триала. Личный
промокод — обычный `PromoCode` с `target_user_id`, бесплатные дни — тип
`winback_days` у существующих одноразовых токенов.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 async/PostgreSQL 18,
Alembic, TaskIQ/Valkey, pytest.

## Global Constraints

- План идёт после «Слоя доставки и согласия»: он опирается на
  `NotificationService.enqueue`, категорию `marketing`, поле
  `User.marketing_opt_out_at` и виды `winback_1`…`winback_4`.
- Ключ дедупликации ступени — `winback:{user_id}:step{n}:{expired_at}`, где
  `expired_at` — `subscription.expires_at.astimezone(UTC).isoformat()`.
- Ступень уходит только тому, кто не отписался от маркетинга и у кого
  подписка всё ещё в статусе `expired`: появление активной подписки
  останавливает лесенку немедленно.
- Повтор лесенки — не чаще `WINBACK_COOLDOWN_DAYS` (умолчание 180). Проверка
  идёт по `winback_grants` и распространяется на все четыре ступени, а не
  только на две с подарком: лесенка кусками бессмысленна.
- Личный промокод не применяется никем, кроме адресата: чужой получает тот же
  `promo_unavailable`, что и по несуществующему коду.
- Повторное нажатие кнопки бесплатных дней не даёт вторых дней: токен
  гасится в той же транзакции, что и начисление.
- Все комментарии и докстринги на русском и объясняют «почему».
- Каждая задача: сначала падающий тест, обязательно запущенный и увиденный
  красным, затем минимальная реализация, затем тематический commit на ветке
  `dev`. Полный `uv run check` — перед сдачей плана.
- Строки не длиннее 100 символов (ruff), переводы строк LF.

---

### Task 1: Учёт выданных лесенок

**Files:**
- Create: `backend/core/src/repibot_core/db/models/winback.py`
- Modify: `backend/core/src/repibot_core/db/models/__init__.py`
- Create: `backend/core/src/repibot_core/db/migrations/versions/0016_winback_grants.py`
- Modify: `backend/core/src/repibot_core/settings.py`
- Create: `backend/core/tests/test_winback.py`

**Interfaces:**
- Produces модель `WinbackGrant(telegram_id, user_id, step, days, granted_at)`,
  настройки `winback_steps_days: tuple[int, ...]`, `winback_promo_percent: int`,
  `winback_promo_ttl_hours: int`, `winback_free_days: int`,
  `winback_cooldown_days: int`.
- Consumes голову миграций `0015` из плана «Слой доставки».

- [ ] **Step 1: Падающий тест уникальности**

`backend/core/tests/test_winback.py`:

```python
"""Лесенка возврата: ступени, подарки и защита от повторов."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User, WinbackGrant

pytestmark = pytest.mark.docker


async def test_same_telegram_cannot_take_a_step_twice(db_session: AsyncSession) -> None:
    """Новая регистрация не должна обнулять счёт: ключ — Telegram, не аккаунт."""
    for _ in range(2):
        db_session.add(WinbackGrant(telegram_id=200_001, user_id=None, step=2, days=0))

    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_user_without_telegram_is_counted_by_account(db_session: AsyncSession) -> None:
    """Почтовый аккаунт тоже нужно ограничить, иначе лесенка бесконечна."""
    user = User(email="wb@example.org", email_verified_at=datetime.now(UTC), referral_code="wb00001")
    db_session.add(user)
    await db_session.flush()
    for _ in range(2):
        db_session.add(WinbackGrant(telegram_id=None, user_id=user.id, step=2, days=0))

    with pytest.raises(IntegrityError):
        await db_session.commit()
```

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_winback.py -q`
Expected: FAIL — `ImportError: cannot import name 'WinbackGrant'`.

- [ ] **Step 3: Модель**

`backend/core/src/repibot_core/db/models/winback.py`:

```python
"""Выданные ступени лесенки возврата.

Ключом служит Telegram, если он привязан, и наш пользователь иначе. Причина
та же, что у trial_grants: флаг на аккаунте обходится удалением аккаунта и
повторной регистрацией, а почту накрутить тривиально.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, func, text
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base


class WinbackGrant(Base):
    __tablename__ = "winback_grants"
    __table_args__ = (
        # Два частичных индекса вместо одного составного: NULL в уникальном
        # индексе Postgres не конфликтует сам с собой, и общий индекс пропустил
        # бы вторую выдачу и по Telegram, и по аккаунту.
        Index(
            "uq_winback_grants_telegram",
            "telegram_id",
            "step",
            unique=True,
            postgresql_where=text("telegram_id IS NOT NULL"),
        ),
        Index(
            "uq_winback_grants_user",
            "user_id",
            "step",
            unique=True,
            postgresql_where=text("telegram_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    step: Mapped[int] = mapped_column(Integer)
    days: Mapped[int] = mapped_column(Integer, default=0)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

Экспортировать `WinbackGrant` из `db/models/__init__.py` рядом с `TrialGrant`.

- [ ] **Step 4: Миграция**

`0016_winback_grants.py`:

```python
"""Учёт выданных ступеней лесенки возврата.

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "winback_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "uq_winback_grants_telegram",
        "winback_grants",
        ["telegram_id", "step"],
        unique=True,
        postgresql_where=sa.text("telegram_id IS NOT NULL"),
    )
    op.create_index(
        "uq_winback_grants_user",
        "winback_grants",
        ["user_id", "step"],
        unique=True,
        postgresql_where=sa.text("telegram_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_winback_grants_user", table_name="winback_grants")
    op.drop_index("uq_winback_grants_telegram", table_name="winback_grants")
    op.drop_table("winback_grants")
```

- [ ] **Step 5: Настройки**

В `settings.py`:

```python
    # Дни ступеней после истечения. Список через запятую, как у остальных
    # перечислений в окружении: NoDecode отключает разбор как JSON.
    winback_steps_days: Annotated[tuple[int, ...], NoDecode] = (1, 3, 14, 30)
    winback_promo_percent: int = Field(default=30, ge=1, le=100)
    winback_promo_ttl_hours: int = Field(default=72, ge=1, le=720)
    winback_free_days: int = Field(default=3, ge=1, le=30)
    winback_cooldown_days: int = Field(default=180, ge=1, le=3650)
```

и валидатор:

```python
    @field_validator("winback_steps_days", mode="before")
    @classmethod
    def _split_winback_steps(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return tuple(int(part) for part in value.split(",") if part.strip())
```

- [ ] **Step 6: Прогнать**

Run: `uv run pytest backend/core/tests/test_winback.py backend/core/tests/test_migrations.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/core/src/repibot_core/db/models/winback.py \
        backend/core/src/repibot_core/db/models/__init__.py \
        backend/core/src/repibot_core/db/migrations/versions/0016_winback_grants.py \
        backend/core/src/repibot_core/settings.py \
        backend/core/tests/test_winback.py
git commit -m "feat: учёт выданных ступеней лесенки по Telegram и аккаунту"
```

---

### Task 2: Личный промокод

**Files:**
- Modify: `backend/core/src/repibot_core/db/models/commerce.py`
- Create: `backend/core/src/repibot_core/db/migrations/versions/0017_promo_target_user.py`
- Modify: `backend/core/src/repibot_core/services/promotions.py:162-176`
- Modify: `backend/core/tests/test_promotions.py`

**Interfaces:**
- Produces `PromoCode.target_user_id: int | None`,
  `PromotionService.prepare(*, user_id, code, gross_rub)` отвергает чужой
  личный код с `ServiceError("промокод недоступен", "promo_unavailable")`.
- Consumes существующий `PromotionService._locked_available`.

- [ ] **Step 1: Падающий тест**

Добавить в `backend/core/tests/test_promotions.py`:

```python
async def test_personal_code_is_refused_to_everyone_else(db_session: AsyncSession) -> None:
    """Код из письма разойдётся по чатам; работать он должен у одного адресата.

    Отказ тот же, что и по несуществующему коду: разный ответ подсказал бы
    подбирающему, что код существует.
    """
    owner = User(email=None, telegram_id=210_001, referral_code="promoown")
    stranger = User(email=None, telegram_id=210_002, referral_code="promostr")
    db_session.add_all([owner, stranger])
    await db_session.flush()
    service = PromotionService(db_session)
    promo = await service.create(PromotionInput(code="COMEBACK", percent_off=30))
    promo.target_user_id = owner.id
    await db_session.commit()

    quote = await service.prepare(
        user_id=owner.id, code="COMEBACK", gross_rub=Decimal("300.00")
    )
    with pytest.raises(ServiceError) as refusal:
        await service.prepare(
            user_id=stranger.id, code="COMEBACK", gross_rub=Decimal("300.00")
        )

    assert quote.discount_rub == Decimal("90.00")
    assert refusal.value.code == "promo_unavailable"
```

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_promotions.py -k personal_code -q`
Expected: FAIL — у `PromoCode` нет `target_user_id`.

- [ ] **Step 3: Поле, миграция, проверка**

В `commerce.py`, в классе `PromoCode`:

```python
    # Непустое значение делает код личным: он не подойдёт никому, кроме
    # адресата. Нужен лесенке возврата, где код уходит в письмо конкретному
    # человеку и оттуда неизбежно разойдётся дальше.
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
```

`0017_promo_target_user.py`:

```python
"""Личный промокод.

Revision ID: 0017
Revises: 0016
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("promo_codes", sa.Column("target_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        None, "promo_codes", "users", ["target_user_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_column("promo_codes", "target_user_id")
```

В `promotions.py` заменить `_locked_available` на принимающий пользователя и
проверяющий адресата:

```python
    async def _locked_available(self, code: str, user_id: int) -> PromoCode:
        now = datetime.now(UTC)
        promo = (
            await self._session.execute(
                select(PromoCode).where(PromoCode.code == code.strip().upper()).with_for_update()
            )
        ).scalar_one_or_none()
        if (
            promo is None
            or not promo.is_active
            or (promo.starts_at is not None and promo.starts_at > now)
            or (promo.expires_at is not None and promo.expires_at <= now)
            # Личный код чужому человеку не показывает даже факта своего
            # существования: ответ тот же, что и по несуществующему коду.
            or (promo.target_user_id is not None and promo.target_user_id != user_id)
        ):
            raise ServiceError("промокод недоступен", "promo_unavailable")
        return promo
```

и поправить единственный вызов в `prepare`:
`promo = await self._locked_available(code, user_id)`.

- [ ] **Step 4: Прогнать**

Run: `uv run pytest backend/core/tests/test_promotions.py backend/core/tests/test_migrations.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/src/repibot_core/db/models/commerce.py \
        backend/core/src/repibot_core/db/migrations/versions/0017_promo_target_user.py \
        backend/core/src/repibot_core/services/promotions.py \
        backend/core/tests/test_promotions.py
git commit -m "feat: личный промокод работает только у адресата"
```

---

### Task 3: Бесплатные дни в одну кнопку

**Files:**
- Modify: `backend/core/src/repibot_core/db/models/one_time_token.py`
- Create: `backend/core/src/repibot_core/db/migrations/versions/0018_winback_token_and_source.py`
- Modify: `backend/core/src/repibot_core/db/models/subscription.py`
- Create: `backend/core/src/repibot_core/services/winback.py`
- Modify: `backend/core/tests/test_winback.py`
- Create: `backend/api/src/repibot_api/routers/winback.py`
- Modify: `backend/api/src/repibot_api/main.py`, `backend/api/src/repibot_api/schemas.py`
- Create: `backend/api/tests/test_winback_routes.py`

**Interfaces:**
- Produces `TokenType.winback_days`, `SubscriptionSource.winback`,
  `SubscriptionEventType.winback`,
  `WinbackService.issue_days_token(user_id: int) -> str`,
  `WinbackService.claim_days(token: str) -> int` (возвращает число начисленных
  дней; бросает `ServiceError(..., "invalid_token")`), маршрут
  `POST /api/winback/claim` с телом `{"token": "..."}` и ответом
  `{"days": 3}`.
- Consumes `SubscriptionService.apply_entitlement`, `PlanRepository`,
  `Settings.winback_free_days`.

- [ ] **Step 1: Падающий тест одноразовости**

Добавить в `backend/core/tests/test_winback.py`:

```python
async def test_free_days_token_works_once(db_session: AsyncSession, month_plan_id: int) -> None:
    """Кнопка в письме нажимается дважды: пальцем и почтовым сканером ссылок."""
    user = User(email=None, telegram_id=200_010, referral_code="wbclaim")
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    service = WinbackService(db_session)
    token = await service.issue_days_token(user.id)
    await db_session.commit()

    granted = await service.claim_days(token)
    await db_session.commit()
    with pytest.raises(ServiceError) as second:
        await service.claim_days(token)

    assert granted == 3
    assert second.value.code == "invalid_token"
```

Фикстуру тарифа взять готовую из `conftest.py`, если подходящая есть; иначе
создать тариф в тесте через `PlanRepository(session).create(...)` тем же
набором полей, что и в `backend/core/tests/test_payment_notifications.py`.

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_winback.py -k free_days -q`
Expected: FAIL — `ModuleNotFoundError: repibot_core.services.winback`.

- [ ] **Step 3: Тип токена и значения перечислений**

В `one_time_token.py` добавить в `TokenType`:

```python
    winback_days = "winback_days"
```

В `subscription.py` добавить `winback = "winback"` в `SubscriptionSource` и в
`SubscriptionEventType`.

`0018_winback_token_and_source.py`:

```python
"""Тип токена и источник дней для лесенки возврата.

Revision ID: 0018
Revises: 0017

Значения нативных перечислений добавляются отдельной миграцией и не
используются в этой же транзакции: Postgres запрещает применять только что
добавленное значение до её конца.
"""

from __future__ import annotations

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter type one_time_token_type add value if not exists 'winback_days'")
    op.execute("alter type subscription_source add value if not exists 'winback'")
    op.execute("alter type subscription_event_type add value if not exists 'winback'")


def downgrade() -> None:
    # Postgres не умеет удалять значение перечисления. Откат оставляет их на
    # месте: они безвредны, а пересоздание типа переписало бы все таблицы,
    # которые на него ссылаются.
    pass
```

Точные имена типов проверить в миграции, где эти перечисления создавались.

- [ ] **Step 4: Сервис**

`backend/core/src/repibot_core/services/winback.py` — часть про токен:

```python
"""Лесенка возврата: подарки и их одноразовость."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    OneTimeToken,
    SubscriptionActor,
    SubscriptionEventType,
    SubscriptionSource,
    TokenType,
    User,
    WinbackGrant,
)
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.services.errors import ServiceError
from repibot_core.services.subscriptions import SubscriptionService
from repibot_core.settings import Settings, get_settings

# Неделя: письмо читают не в день получения, а кнопка без срока превращается
# в вечный купон, который однажды найдут в архиве переписки.
DAYS_TOKEN_TTL = timedelta(days=7)


class WinbackService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._plans = PlanRepository(session)
        self._subscriptions = SubscriptionRepository(session)

    async def issue_days_token(self, user_id: int) -> str:
        raw = secrets.token_urlsafe(32)
        self._session.add(
            OneTimeToken(
                type=TokenType.winback_days,
                user_id=user_id,
                token_hash=sha256(raw.encode()).hexdigest(),
                payload={"days": self._settings.winback_free_days},
                expires_at=datetime.now(UTC) + DAYS_TOKEN_TTL,
            )
        )
        await self._session.flush()
        return raw

    async def claim_days(self, token: str) -> int:
        """Гасит токен и начисляет дни в одной транзакции.

        Порядок именно такой: сначала блокируется и гасится токен, и только
        потом начисляются дни. Обратный порядок дал бы вторые дни двум
        одновременным нажатиям — почтовый сканер ссылок ходит вместе с
        человеком.
        """
        now = datetime.now(UTC)
        found = (
            await self._session.execute(
                select(OneTimeToken)
                .where(
                    OneTimeToken.token_hash == sha256(token.encode()).hexdigest(),
                    OneTimeToken.type == TokenType.winback_days,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if found is None or found.used_at is not None or found.expires_at <= now:
            raise ServiceError("ссылка недействительна", "invalid_token")
        found.used_at = now

        days = int((found.payload or {}).get("days", self._settings.winback_free_days))
        subscription = await self._subscriptions.get_for_user_for_update(found.user_id)
        plan_id = subscription.plan_id if subscription is not None else None
        plan = await self._plans.get(plan_id) if plan_id is not None else None
        if plan is None:
            plan = await self._cheapest_visible_plan()
        if plan is None:
            raise ServiceError("нет тарифа для начисления", "plan_not_found")

        await SubscriptionService(
            self._session, self._settings, provisioning=None
        ).apply_entitlement(
            found.user_id,
            plan,
            days,
            source=SubscriptionSource.winback,
            event_type=SubscriptionEventType.winback,
            actor=SubscriptionActor.system,
            origin_attempt_id=None,
        )
        user = await self._session.get(User, found.user_id)
        self._session.add(
            WinbackGrant(
                telegram_id=user.telegram_id if user is not None else None,
                user_id=found.user_id,
                step=self._settings.winback_steps_days.index(
                    sorted(self._settings.winback_steps_days)[2]
                )
                + 1,
                days=days,
            )
        )
        await self._session.flush()
        return days
```

Замечание к последнему блоку: номер ступени вычисляется здесь только потому,
что токен приходит без него. Проще и надёжнее положить номер в
`payload` при выпуске: `payload={"days": ..., "step": step}` — так и сделать,
а вычисление по индексу убрать. `issue_days_token` тогда принимает
`(user_id: int, step: int)`.

Дописать метод `_cheapest_visible_plan`, возвращающий самый дешёвый активный
видимый неtrial-тариф: он нужен тем, у кого подписки нет вовсе, — начислять
дни без тарифа некуда. Запрос — `select(Plan).where(Plan.is_active,
Plan.is_visible, Plan.is_trial.is_(False)).order_by(Plan.price_rub).limit(1)`.

- [ ] **Step 5: Маршрут**

`backend/api/src/repibot_api/routers/winback.py`:

```python
"""Получение подарочных дней лесенки возврата по одноразовому токену."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import AuthContext, current_context, db_session
from repibot_api.errors import api_error_from
from repibot_api.schemas import WinbackClaimRequest, WinbackClaimResponse
from repibot_core.services.errors import ServiceError
from repibot_core.services.winback import WinbackService

router = APIRouter(prefix="/api/winback", tags=["winback"])


@router.post("/claim", response_model=WinbackClaimResponse)
async def claim(
    payload: WinbackClaimRequest,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> WinbackClaimResponse:
    """Требует входа намеренно: дни начисляются на аккаунт, и он должен быть свой.

    Токен доказывает право на подарок, но не личность: ссылка из письма могла
    попасть куда угодно вместе с самим письмом.
    """
    try:
        days = await WinbackService(session).claim_days(payload.token)
    except ServiceError as error:
        raise api_error_from(error) from error
    await session.commit()
    return WinbackClaimResponse(days=days)
```

Проверить в `claim_days`, что `found.user_id == context.principal.user_id`;
если нет — тот же `invalid_token`. Передать идентификатор параметром:
`claim_days(token, user_id)`.

Схемы в `schemas.py`:

```python
class WinbackClaimRequest(BaseModel):
    token: str


class WinbackClaimResponse(BaseModel):
    days: int
```

Зарегистрировать роутер в `main.py`.

- [ ] **Step 6: Тест маршрута**

`backend/api/tests/test_winback_routes.py`: вошедший пользователь получает
дни один раз, второй запрос отвечает 400 с `invalid_token`, чужой
пользователь с тем же токеном получает 400.

- [ ] **Step 7: Прогнать**

Run: `uv run pytest backend/core/tests/test_winback.py backend/api/tests/test_winback_routes.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/core/src/repibot_core/db/models/one_time_token.py \
        backend/core/src/repibot_core/db/models/subscription.py \
        backend/core/src/repibot_core/db/migrations/versions/0018_winback_token_and_source.py \
        backend/core/src/repibot_core/services/winback.py \
        backend/api/src/repibot_api/routers/winback.py \
        backend/api/src/repibot_api/main.py \
        backend/api/src/repibot_api/schemas.py \
        backend/core/tests/test_winback.py \
        backend/api/tests/test_winback_routes.py
git commit -m "feat: бесплатные дни лесенки по одноразовому токену"
```

---

### Task 4: Крон лесенки

**Files:**
- Modify: `backend/core/src/repibot_core/services/winback.py`
- Modify: `backend/core/src/repibot_core/i18n.py`
- Modify: `backend/core/src/repibot_core/tasks.py`
- Modify: `backend/core/tests/test_winback.py`

**Interfaces:**
- Produces `WinbackService.run(*, now: datetime) -> int`, задачу
  `run_winback` с расписанием `"23 9 * * *"`.
- Consumes `NotificationService.enqueue`, `PromotionService.create`,
  `WinbackService.issue_days_token`, `WinbackGrant`.

- [ ] **Step 1: Падающий тест ступеней**

```python
async def test_ladder_walks_its_steps_once_each(db_session: AsyncSession) -> None:
    """Четыре касания за месяц, каждое по одному разу на дату истечения."""
    subscription = await _expired_subscriber(db_session, days_ago=1, telegram_id=200_020)
    service = WinbackService(db_session)

    first = await service.run(now=datetime.now(UTC))
    again = await service.run(now=datetime.now(UTC))
    await db_session.commit()

    kinds = list((await db_session.scalars(select(NotificationDelivery.kind))).all())
    assert (first, again) == (1, 0)
    assert kinds == ["winback_1"]
    assert subscription.id > 0


async def test_active_subscription_stops_the_ladder(db_session: AsyncSession) -> None:
    """Человек вернулся — предлагать ему вернуться незачем."""
    subscription = await _expired_subscriber(db_session, days_ago=3, telegram_id=200_021)
    subscription.status = SubscriptionState.active
    subscription.expires_at = datetime.now(UTC) + timedelta(days=30)
    await db_session.commit()

    staged = await WinbackService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    assert staged == 0


async def test_opted_out_user_gets_no_ladder(db_session: AsyncSession) -> None:
    subscription = await _expired_subscriber(db_session, days_ago=1, telegram_id=200_022)
    user = await db_session.get(User, subscription.user_id)
    assert user is not None
    user.marketing_opt_out_at = datetime.now(UTC)
    await db_session.commit()

    staged = await WinbackService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    assert staged == 0


async def test_cooldown_blocks_a_second_ladder(db_session: AsyncSession) -> None:
    """Полгода между лесенками: иначе истечение превращается в способ заработка."""
    subscription = await _expired_subscriber(db_session, days_ago=1, telegram_id=200_023)
    db_session.add(
        WinbackGrant(telegram_id=200_023, user_id=subscription.user_id, step=2, days=0)
    )
    await db_session.commit()

    staged = await WinbackService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    assert staged == 0
```

Вспомогательную функцию `_expired_subscriber(session, *, days_ago, telegram_id)`
написать по образцу `_subscriber` из
`backend/core/tests/test_subscription_notices.py`: тот же тариф, статус
`SubscriptionState.expired`, `expires_at = now - timedelta(days=days_ago)`.

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_winback.py -k ladder -q`
Expected: FAIL — у `WinbackService` нет метода `run`.

- [ ] **Step 3: Реализация**

Добавить в `WinbackService`:

```python
    async def run(self, *, now: datetime) -> int:
        """Ставит ту ступень, чей день совпал с сегодняшним.

        Ступень выбирается по числу полных суток с даты окончания, а не по
        счётчику в базе: крон может не отработать сутки, и счётчик увёл бы
        человека на ступень, до которой ещё не дошло время.
        """
        staged = 0
        for number, offset in enumerate(sorted(self._settings.winback_steps_days), start=1):
            border = now - timedelta(days=offset)
            rows = (
                await self._session.execute(
                    select(Subscription).where(
                        Subscription.status == SubscriptionState.expired,
                        Subscription.expires_at > border - timedelta(days=1),
                        Subscription.expires_at <= border,
                    )
                )
            ).scalars()
            for subscription in rows:
                if await self._blocked(subscription.user_id, now):
                    continue
                staged += await self._step(subscription, number, now)
        return staged

    async def _blocked(self, user_id: int, now: datetime) -> bool:
        """Отписка и кулдаун — единственные причины пропустить ступень."""
        user = await self._session.get(User, user_id)
        if user is None or user.marketing_opt_out_at is not None:
            return True
        border = now - timedelta(days=self._settings.winback_cooldown_days)
        # Личность лесенки — Telegram, если он привязан, и аккаунт иначе. Та
        # же развилка, что и при записи выдачи: иначе счётчик и проверка
        # смотрели бы на разные строки.
        if user.telegram_id is not None:
            identity = WinbackGrant.telegram_id == user.telegram_id
        else:
            identity = WinbackGrant.user_id == user_id
        last = await self._session.scalar(
            select(func.max(WinbackGrant.granted_at)).where(identity)
        )
        return last is not None and last > border

    async def _step(self, subscription: Subscription, number: int, now: datetime) -> int:
        """Собирает подарок ступени и ставит уведомление одним ключом."""
        expired_at = subscription.expires_at.astimezone(UTC).isoformat()
        params: dict[str, object] = {}
        if number == 2:
            params["code"] = await self._personal_promo(subscription.user_id, now)
        if number == 3:
            token = await self.issue_days_token(subscription.user_id, step=number)
            params["link"] = f"{self._settings.public_app_url}/winback?token={token}"
            params["days"] = self._settings.winback_free_days
        staged = await NotificationService(self._session).enqueue(
            user_id=subscription.user_id,
            kind=f"winback_{number}",
            dedup_key=f"winback:{subscription.user_id}:step{number}:{expired_at}",
            params=params,
        )
        if staged and number in (2, 3):
            user = await self._session.get(User, subscription.user_id)
            self._session.add(
                WinbackGrant(
                    telegram_id=user.telegram_id if user is not None else None,
                    user_id=subscription.user_id,
                    step=number,
                    days=self._settings.winback_free_days if number == 3 else 0,
                )
            )
            await self._session.flush()
        return staged

    async def _personal_promo(self, user_id: int, now: datetime) -> str:
        """Код виден адресату и бесполезен всем прочим."""
        code = f"BACK{secrets.token_hex(3).upper()}"
        promo = await PromotionService(self._session).create(
            PromotionInput(
                code=code,
                percent_off=self._settings.winback_promo_percent,
                per_user_limit=1,
                expires_at=now + timedelta(hours=self._settings.winback_promo_ttl_hours),
            )
        )
        promo.target_user_id = user_id
        await self._session.flush()
        return code
```

Замечание: ступень 3 — та, что даёт бесплатные дни, при умолчании
`1,3,14,30`. Номер вычисляется порядковым номером в отсортированном списке,
поэтому изменение порогов не ломает соответствие «вторая ступень —
промокод, третья — дни».

Импорты: `from sqlalchemy import func, select`,
`from repibot_core.db.models import Subscription`,
`from repibot_core.domain.subscriptions import SubscriptionState`,
`from repibot_core.services.notifications import NotificationService`,
`from repibot_core.services.promotions import PromotionInput, PromotionService`.

Поправить сигнатуру `issue_days_token(self, user_id: int, *, step: int) -> str`
и класть `step` в `payload`.

- [ ] **Step 4: Тексты ступеней (уже на месте — только проверить)**

Ключи `winback.step1`…`winback.step4` в вариантах `.bot`, `.subject` и `.body`
на обоих языках уже добавлены в `i18n.py` вместе с реестром видов: вид без
текстов падает в `translate` у живого человека, и их завели сразу под
проверкой `test_every_declared_kind_has_texts_in_every_language`.

Ничего не добавляй. Открой `i18n.py` и сверь подстановки с тем, что передаёт
твой `_step`: у первой и четвёртой ступени подстановок нет вовсе, у второй —
`{percent}` и `{code}`, у третьей — `{days}` и `{link}`. Расхождение здесь
даёт `KeyError` на живом письме, поэтому сверять нужно глазами, а не
предполагать. Ниже — тексты, которые там должны лежать. Русские:

```python
        "winback.step1.bot": (
            "Подписка закончилась вчера. Вернуть доступ можно в один шаг — "
            "тариф и оплата на месте."
        ),
        "winback.step2.bot": (
            "Держите личную скидку {percent}% на возвращение: код {code}. "
            "Он ваш и действует трое суток."
        ),
        "winback.step3.bot": (
            "Возвращаем {days} дня доступа просто так. Забрать: {link}"
        ),
        "winback.step4.bot": (
            "Это последнее письмо о подписке. Если захотите вернуться — "
            "мы на месте, ничего делать заранее не нужно."
        ),
```

Тема и тело письма — те же формулировки с обращением на «вы» и без
сокращений. Ключ `percent` добавить в `params` ступени 2 рядом с `code`.

- [ ] **Step 5: Задача**

В `tasks.py`:

```python
@broker.task(schedule=[{"cron": "23 9 * * *"}])
async def run_winback() -> dict[str, int]:
    """Ставит очередную ступень лесенки возврата.

    Раз в сутки и в дневное время: письмо про возвращение, пришедшее ночью,
    к утру уже погребено под остальной почтой.
    """
    from repibot_core.services.winback import WinbackService

    engine = create_engine(get_settings().database_url)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            staged = await WinbackService(session).run(now=datetime.now(UTC))
            await session.commit()
    finally:
        await engine.dispose()
    return {"staged": staged}
```

- [ ] **Step 6: Прогнать**

Run: `uv run pytest backend/core/tests/test_winback.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/core/src/repibot_core/services/winback.py \
        backend/core/src/repibot_core/i18n.py \
        backend/core/src/repibot_core/tasks.py \
        backend/core/tests/test_winback.py
git commit -m "feat: суточный крон лесенки возврата с подарками"
```

---

### Task 5: Экран получения дней и документация

**Files:**
- Create: `frontend/apps/miniapp/src/routes/winback.tsx`
- Create: `frontend/apps/miniapp/src/routes/winback.test.tsx`
- Modify: `frontend/apps/miniapp/src/router.tsx`
- Create: `frontend/apps/web/src/app/winback/page.tsx`
- Modify: `frontend/packages/core/src/i18n/ru.ts`, `frontend/packages/core/src/i18n/en.ts`
- Modify: `docs/deployment.md`

**Interfaces:**
- Consumes `POST /api/winback/claim` из задачи 3.

- [ ] **Step 1: Падающий тест экрана**

`frontend/apps/miniapp/src/routes/winback.test.tsx`: экран с токеном в строке
запроса отправляет `POST /api/winback/claim`, показывает «Начислено 3 дня»,
а при ответе 400 показывает текст про недействительную ссылку. Обёртку и
подмену сети взять из `frontend/apps/miniapp/src/routes/payments.test.tsx`.

- [ ] **Step 2: Запустить и увидеть падение**

Run: `cd frontend && pnpm --filter miniapp test winback`
Expected: FAIL — модуля маршрута нет.

- [ ] **Step 3: Экраны**

`routes/winback.tsx` — маршрут `/winback`, читающий `token` из
`useSearch`, вызывающий мутацию при монтировании ровно один раз и
показывающий три состояния: идёт, начислено, ссылка недействительна.
Зарегистрировать маршрут в `router.tsx` рядом с остальными.

`frontend/apps/web/src/app/winback/page.tsx` — то же самое для кабинета;
страница внутри гейта, потому что маршрут требует входа.

- [ ] **Step 4: Переводы**

Ключи `winback.claiming`, `winback.claimed`, `winback.invalid` в `ru.ts` и
`en.ts`.

- [ ] **Step 5: Документация**

В `docs/deployment.md` добавить пять переменных лесенки из раздела 10
спецификации и строку расписания `run_winback` — ежедневно в 9:23 UTC.

- [ ] **Step 6: Полная проверка**

Run: `uv run check`
Expected: все восемь проверок зелёные.

- [ ] **Step 7: Commit**

```bash
git add frontend/apps/miniapp/src/routes/winback.tsx \
        frontend/apps/miniapp/src/routes/winback.test.tsx \
        frontend/apps/miniapp/src/router.tsx \
        frontend/apps/web/src/app/winback/page.tsx \
        frontend/packages/core/src/i18n \
        docs/deployment.md
git commit -m "feat: экран получения подарочных дней"
```

---

## Plan Self-Review

**Покрытие спецификации.** Раздел 7 закрыт целиком: таблица из четырёх
ступеней — задача 4, личный промокод с `target_user_id` и сроком 72 часа —
задачи 2 и 4, бесплатные дни по токену со сроком 7 суток — задача 3,
кулдаун 180 дней по `winback_grants` — задачи 1 и 4, остановка лесенки при
возвращении и при отписке — задача 4. Раздел 3 «Лесенка» — задачи 1–3.
Настройки раздела 10 — задача 1, документация — задача 5.

**Заглушки.** Не найдено. Два места в задаче 3 намеренно исправляют сами
себя по ходу: номер ступени переезжает в `payload` токена, а `claim_days`
получает идентификатор вошедшего. Оба исправления записаны явно, а не
оставлены на догадку.

**Согласованность имён.** `WinbackGrant(telegram_id, user_id, step, days,
granted_at)` — одна форма в задачах 1, 3 и 4. `issue_days_token(user_id, *,
step)` и `claim_days(token, user_id)` — окончательные сигнатуры, ими же
пользуются маршрут и крон. Виды `winback_1`…`winback_4` совпадают с реестром
`_KINDS` плана «Слой доставки», их `text_key` — `winback.step1`…`winback.step4` —
с ключами i18n задачи 4.
