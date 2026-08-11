"""Лесенка возврата: подарки и их одноразовость."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    NotificationDelivery,
    OneTimeToken,
    Plan,
    Subscription,
    SubscriptionActor,
    SubscriptionEventType,
    SubscriptionSource,
    TokenType,
    User,
    WinbackGrant,
)
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.services.errors import ServiceError
from repibot_core.services.notifications import RELATIVE_LINK, NotificationService
from repibot_core.services.promotions import PromotionInput, PromotionService
from repibot_core.services.subscriptions import SubscriptionService
from repibot_core.settings import Settings, get_settings

# Пороги и размеры подарков живут здесь, пока их не перенесли в настройки.
# Значение в коде честнее пустого чтения из Settings: так видно, что величина
# ещё не настраивается окружением.

# Неделя: письмо читают не в день получения, а кнопка без срока превращается
# в вечный купон, который однажды найдут в архиве переписки.
DAYS_TOKEN_TTL = timedelta(days=7)

# Ступени с подарком: вторая шлёт личный промокод, третья — бесплатные дни.
# Номер ступени — это порядковый номер порога в отсортированном списке, а не
# сам порог, поэтому сдвиг порогов в окружении не рассыпает соответствие.
PROMO_STEP = 2
DAYS_STEP = 3


class WinbackService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._plans = PlanRepository(session)
        self._subscriptions = SubscriptionRepository(session)

    async def run(self, *, now: datetime) -> int:
        """Ставит ту ступень, чей день совпал с сегодняшним.

        Ступень выбирается по числу полных суток с даты окончания, а не по
        счётчику в базе: крон может не отработать сутки, и счётчик увёл бы
        человека на ступень, до которой ещё не дошло время.

        Окно выборки — ровно сутки вокруг порога. Без него пропущенный прогон
        превращался бы в рассылку по всем, кто ушёл когда-либо, а сам обход —
        в ежесуточный проход по таблице, которая только растёт.
        """
        staged = 0
        for number, offset in enumerate(sorted(self._settings.winback_steps_days), start=1):
            border = now - timedelta(days=offset)
            rows = (
                (
                    await self._session.execute(
                        select(Subscription).where(
                            Subscription.status == SubscriptionState.expired,
                            Subscription.expires_at > border - timedelta(days=1),
                            Subscription.expires_at <= border,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for subscription in rows:
                if await self._blocked(subscription):
                    continue
                staged += await self._step(subscription, number, now)
        return staged

    async def _blocked(self, subscription: Subscription) -> bool:
        """Отписка и кулдаун — единственные причины пропустить ступень.

        Кулдаун отсчитывается от даты окончания подписки, а не от «сегодня», и
        смотрит только на выдачи, случившиеся до неё. Иначе лесенка глушила бы
        сама себя: подарок второй ступени попадал бы в тот же кулдаун и
        отменял третью с четвёртой, до которых человек не дошёл бы никогда.
        """
        user = await self._session.get(User, subscription.user_id)
        if user is None or user.marketing_opt_out_at is not None:
            return True
        started = subscription.expires_at
        last = await self._session.scalar(
            select(func.max(WinbackGrant.granted_at)).where(
                self._identity(user.telegram_id, subscription.user_id),
                WinbackGrant.granted_at <= started,
            )
        )
        return last is not None and last > started - timedelta(
            days=self._settings.winback_cooldown_days
        )

    async def _step(self, subscription: Subscription, number: int, now: datetime) -> int:
        """Собирает подарок ступени и ставит уведомление одним ключом."""
        expired_at = subscription.expires_at.astimezone(UTC).isoformat()
        dedup_key = f"winback:{subscription.user_id}:step{number}:{expired_at}"
        if await self._already_staged(dedup_key):
            return 0
        params: dict[str, object] = {}
        if number == PROMO_STEP:
            params["percent"] = self._settings.winback_promo_percent
            params["code"] = await self._personal_promo(subscription.user_id, now)
        if number == DAYS_STEP:
            token = await self.issue_days_token(subscription.user_id, step=number)
            params["days"] = self._settings.winback_free_days
            # Путь, а не готовая ссылка: адрес выберет слой доставки по каналу.
            # Ссылка на Mini App, ушедшая письмом, не откроется в браузере.
            params[RELATIVE_LINK] = f"/winback?token={token}"
        staged = await NotificationService(self._session).enqueue(
            user_id=subscription.user_id,
            kind=f"winback_{number}",
            dedup_key=dedup_key,
            params=params,
        )
        if staged and number in (PROMO_STEP, DAYS_STEP):
            # Дни здесь нулевые: письмо ничего не начислило, оно лишь показало
            # кнопку. Настоящее число проставит получение подарка, а строка
            # нужна уже сейчас — по ней считается кулдаун следующей лесенки.
            await self._record_grant(subscription.user_id, step=number, days=0, now=now)
        return staged

    async def _already_staged(self, dedup_key: str) -> bool:
        """Письмо этой ступени уже поставлено в очередь.

        Повтор доставки ловит и уникальный индекс, но промокод с токеном
        выпускаются раньше него: без этой проверки второй прогон в те же сутки
        оставлял бы в базе код и кнопку, которых человек никогда не увидит.
        """
        found = await self._session.scalar(
            select(NotificationDelivery.id)
            .where(NotificationDelivery.dedup_key == dedup_key)
            .limit(1)
        )
        return found is not None

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
        await self._record_grant(user_id, step=step, days=days, now=now)
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

    @staticmethod
    def _identity(telegram_id: int | None, user_id: int | None) -> ColumnElement[bool]:
        """Личность лесенки — Telegram, если он привязан, и аккаунт иначе.

        Та же развилка, что и в уникальных индексах: иначе поиск и запись
        смотрели бы на разные строки, и счёт выдач обходился бы регистрацией
        нового аккаунта на тот же Telegram.
        """
        if telegram_id is not None:
            return WinbackGrant.telegram_id == telegram_id
        return WinbackGrant.telegram_id.is_(None) & (WinbackGrant.user_id == user_id)

    async def _record_grant(self, user_id: int, *, step: int, days: int, now: datetime) -> None:
        """Отмечает выданную ступень — по ней считается полугодовой кулдаун.

        Строка ступени может уже существовать: лесенка записывает её, когда
        отправляет письмо, а не когда человек нажимает кнопку, и та же ступень
        могла достаться человеку прошлой лесенкой полгода назад. Поэтому здесь
        обновление, а не вставка: второй строке не дал бы появиться уникальный
        индекс, и упал бы весь прогон крона, а не один адресат.

        Отметка времени переезжает на свежую выдачу вместе с днями. Оставить
        прошлогоднюю значит считать кулдаун от позапрошлой лесенки — и пустить
        следующую сразу же.
        """
        user = await self._session.get(User, user_id)
        telegram_id = None if user is None else user.telegram_id
        identity = self._identity(telegram_id, user_id)
        grant = (
            await self._session.execute(
                select(WinbackGrant).where(identity, WinbackGrant.step == step).with_for_update()
            )
        ).scalar_one_or_none()
        if grant is None:
            self._session.add(
                WinbackGrant(
                    telegram_id=telegram_id,
                    user_id=user_id,
                    step=step,
                    days=days,
                    granted_at=now,
                )
            )
        else:
            grant.days, grant.granted_at = days, now
