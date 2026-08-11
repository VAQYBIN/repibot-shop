"""Лесенка возврата: подарки и их одноразовость."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    OneTimeToken,
    Plan,
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

# Пороги и размеры подарков живут здесь, пока их не перенесли в настройки.
# Значение в коде честнее пустого чтения из Settings: так видно, что величина
# ещё не настраивается окружением.

# Неделя: письмо читают не в день получения, а кнопка без срока превращается
# в вечный купон, который однажды найдут в архиве переписки.
DAYS_TOKEN_TTL = timedelta(days=7)


class WinbackService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._plans = PlanRepository(session)
        self._subscriptions = SubscriptionRepository(session)

    async def issue_days_token(self, user_id: int, *, step: int) -> str:
        """Выпускает кнопку подарочных дней для конкретной ступени.

        Ступень кладётся в токен, а не вычисляется при получении: к моменту
        нажатия пороги в настройках могут поехать, и выдача записалась бы не
        на ту ступень, за которую человеку прислали письмо.
        """
        raw = secrets.token_urlsafe(32)
        self._session.add(
            OneTimeToken(
                type=TokenType.winback_days,
                user_id=user_id,
                token_hash=sha256(raw.encode()).hexdigest(),
                payload={"days": self._settings.winback_free_days, "step": step},
                expires_at=datetime.now(UTC) + DAYS_TOKEN_TTL,
            )
        )
        await self._session.flush()
        return raw

    async def claim_days(self, token: str, user_id: int) -> int:
        """Гасит токен и начисляет дни в одной транзакции.

        Порядок именно такой: сначала блокируется и гасится токен, и только
        потом начисляются дни. Обратный порядок дал бы вторые дни двум
        одновременным нажатиям — почтовый сканер ссылок ходит вместе с
        человеком.

        Идентификатор вошедшего сверяется с адресатом токена: токен доказывает
        право на подарок, но не личность — ссылка из письма могла уехать
        дальше вместе с самим письмом.
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
        payload: dict[str, Any] = {} if found is None else (found.payload or {})
        if (
            found is None
            or found.user_id != user_id
            or found.used_at is not None
            or found.expires_at <= now
            # Токен без дней и ступени выпущен не нами: угаданная ступень
            # записала бы выдачу не в тот счёт, по которому считается кулдаун.
            or "days" not in payload
            or "step" not in payload
        ):
            raise ServiceError("ссылка недействительна", "invalid_token")
        found.used_at = now

        days, step = int(payload["days"]), int(payload["step"])
        subscription = await self._subscriptions.get_for_user_for_update(user_id)
        plan = None if subscription is None else await self._plans.get(subscription.plan_id)
        if plan is None:
            plan = await self._cheapest_visible_plan()
        if plan is None:
            raise ServiceError("нет тарифа для начисления", "plan_not_found")

        await SubscriptionService(
            self._session, self._settings, provisioning=None
        ).apply_entitlement(
            user_id,
            plan,
            days,
            source=SubscriptionSource.winback,
            event_type=SubscriptionEventType.winback,
            actor=SubscriptionActor.system,
            origin_attempt_id=None,
        )
        await self._record_grant(user_id, step=step, days=days)
        await self._session.flush()
        return days

    async def _cheapest_visible_plan(self) -> Plan | None:
        """Тариф тому, у кого подписки нет вовсе: начислять дни некуда.

        Самый дешёвый из витрины, потому что подарок не должен выглядеть
        обещанием дорогого тарифа, за который человек не платил.
        """
        found = await self._session.execute(
            select(Plan)
            .where(Plan.is_active, Plan.is_visible, Plan.is_trial.is_(False))
            .order_by(Plan.price_rub)
            .limit(1)
        )
        return found.scalar_one_or_none()

    async def _record_grant(self, user_id: int, *, step: int, days: int) -> None:
        """Отмечает выданную ступень — по ней считается полугодовой кулдаун.

        Строка ступени может уже существовать: лесенка записывает её, когда
        отправляет письмо, а не когда человек нажимает кнопку. Тогда выдача
        дополняется числом дней, а не дублируется — второй строке не дал бы
        появиться уникальный индекс.
        """
        user = await self._session.get(User, user_id)
        telegram_id = None if user is None else user.telegram_id
        # Личность лесенки — Telegram, если он привязан, и аккаунт иначе. Та же
        # развилка, что и в уникальных индексах: иначе поиск и запись смотрели
        # бы на разные строки.
        identity: ColumnElement[bool] = (
            WinbackGrant.telegram_id == telegram_id
            if telegram_id is not None
            else WinbackGrant.telegram_id.is_(None) & (WinbackGrant.user_id == user_id)
        )
        grant = (
            await self._session.execute(
                select(WinbackGrant).where(identity, WinbackGrant.step == step).with_for_update()
            )
        ).scalar_one_or_none()
        if grant is None:
            self._session.add(
                WinbackGrant(telegram_id=telegram_id, user_id=user_id, step=step, days=days)
            )
        else:
            grant.days = days
