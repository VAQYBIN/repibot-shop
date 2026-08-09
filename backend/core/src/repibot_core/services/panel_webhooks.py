"""Приём событий панели.

Панель рассказывает о своих изменениях, но источником истины от этого не
становится: сроки считаем мы, а её сообщение — только повод сверить состояние.
Поэтому обработка сводится к трём вещам — записать событие целиком, не
обработать его дважды и поставить задачу примирения, если панель могла
разойтись с нами.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User, WebhookSource
from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.db.repositories.webhooks import WebhookRepository
from repibot_core.services.panel_cache import PanelCache, devices_key
from repibot_core.services.provisioning import TOPIC_PROVISION

logger = logging.getLogger(__name__)

# События, после которых панель может расходиться с нашим состоянием.
_RECONCILE = frozenset(
    {
        "user.revoked",
        "user.modified",
        "user.deleted",
        "user.disabled",
        "user.enabled",
        "user.limited",
        "user.expired",
    }
)
# События, после которых наш кэш устройств заведомо устарел.
_DEVICES = frozenset({"user_hwid_devices.added", "user_hwid_devices.deleted"})

# Панель подписывает тело шестнадцатеричным HMAC-SHA256; префикс схемы в
# заголовке необязателен, но встречается, и снимать его надо до сравнения.
_SIGNATURE_PREFIX = "sha256="


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    """Подпись сверяется по сырому телу, до разбора JSON.

    Пересобранный из объекта JSON отличается от присланного пробелами и
    порядком ключей, и подпись перестала бы сходиться на ровном месте.

    Пустой секрет означает «вебхуки не настроены»: принимать неподписанные
    события опаснее, чем не принимать никаких.
    """
    if not secret or header is None:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # compare_digest, а не ==: сравнение за постоянное время не даёт подобрать
    # подпись по времени ответа.
    return hmac.compare_digest(expected, header.strip().removeprefix(_SIGNATURE_PREFIX))


class PanelWebhookService:
    def __init__(self, session: AsyncSession, cache: PanelCache) -> None:
        self._session = session
        self._cache = cache
        self._webhooks = WebhookRepository(session)
        self._outbox = OutboxRepository(session)

    async def handle(self, payload: dict[str, Any], *, now: datetime | None = None) -> bool:
        """Разбирает одно событие. `False` — такое уже принимали.

        **Дату окончания подписки не двигает ни одно событие панели.** Панель
        сообщает, что у неё изменилось, а не что мы должны продать: `expired`,
        `limited` и `revoked` — повод привести панель к нашему состоянию, а не
        переписать наше по её словам. Иначе чужая правка в панели или повтор
        доставки становились бы биллинговой операцией.
        """
        moment = now or datetime.now(UTC)
        event = str(payload.get("event") or "")
        panel_id = _panel_id(payload)

        # Своего идентификатора события панель не присылает, поэтому ключ
        # собирается из того, что повторная доставка сохраняет неизменным.
        stored = await self._webhooks.remember(
            source=WebhookSource.remnawave,
            event_id=f"{event}:{payload.get('timestamp') or ''}:{panel_id}",
            event=event[:64],
            payload=payload,
            now=moment,
        )
        if stored is None:
            return False

        user = await self._find_user(panel_id)
        if user is None:
            # Пользователь панели, заведённый мимо нас: событие сохраняем, но
            # реагировать нечем — своей подписки за ним не стоит.
            logger.info(
                "событие панели о неизвестном пользователе", extra={"panel_user_id": panel_id}
            )
        elif event in _RECONCILE:
            # Не правим панель прямо здесь: приём вебхука должен закончиться
            # быстро и не зависеть от доступности панели, а повтор задачи из
            # очереди безопасен — примирение идемпотентно.
            await self._outbox.add(TOPIC_PROVISION, {"user_id": user.id})
        elif event in _DEVICES:
            # Список устройств у нас не хранится, только кэшируется; гасим его,
            # чтобы экран показал изменение сразу, а не через минуту.
            await self._cache.drop(devices_key(user.id))

        await self._webhooks.mark_processed(stored, moment)
        await self._session.commit()
        return True

    async def _find_user(self, panel_id: str) -> User | None:
        """Ищет нашего пользователя по идентификатору панели.

        Запрос здесь, а не в `UserRepository`: обратное направление нужно
        только приёму вебхуков — во всех остальных местах мы идём от своего
        пользователя к панели, а не наоборот.
        """
        if not panel_id.isdigit():
            return None
        statement = select(User).where(User.remnawave_id == int(panel_id))
        return (await self._session.execute(statement)).scalar_one_or_none()


def _panel_id(payload: dict[str, Any]) -> str:
    """Идентификатор пользователя панели из тела события.

    У событий пользователя `data` — сам пользователь, у событий устройств он
    лежит в `data.user`. Строка, а не число: тело чужое, и непонятное значение
    должно попасть в ключ события как есть, а не уронить приём.
    """
    data = payload.get("data")
    if not isinstance(data, dict):
        return ""
    nested = data.get("user")
    holder: dict[str, Any] = nested if isinstance(nested, dict) else data
    found = holder.get("id")
    return "" if found is None else str(found)
