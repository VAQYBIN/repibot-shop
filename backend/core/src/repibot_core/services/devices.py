"""Устройства пользователя.

Свои устройства человек отвязывает сам: иначе смена телефона превращается в
обращение в поддержку. Список читается из панели и кэшируется — экран кабинета
опрашивают часто, а меняется он редко.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.integrations.remnawave.client import RemnawaveRejected
from repibot_core.integrations.remnawave.devices import PanelDevices
from repibot_core.services.errors import ServiceError
from repibot_core.services.panel_cache import PanelCache, devices_key


@dataclass(frozen=True, slots=True)
class DeviceView:
    hwid: str
    platform: str | None
    device_model: str | None
    os_version: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DevicesView:
    devices: list[DeviceView]
    limit: int
    used: int


class DeviceService:
    def __init__(self, session: AsyncSession, devices: PanelDevices, cache: PanelCache) -> None:
        self._session = session
        self._panel = devices
        self._cache = cache
        self._users = UserRepository(session)
        self._subscriptions = SubscriptionRepository(session)
        self._plans = PlanRepository(session)

    async def list(self, user_id: int) -> DevicesView:
        panel_id, limit = await self._context(user_id)
        raw = await self._cached(user_id, panel_id)
        devices = [_view(item) for item in raw]
        return DevicesView(devices=devices, limit=limit, used=len(devices))

    async def unlink(self, user_id: int, hwid: str) -> None:
        panel_id, _ = await self._context(user_id)
        try:
            await self._panel.delete(panel_id, hwid)
        except RemnawaveRejected as error:
            # Панель отвечает отказом и на чужой hwid, и на несуществующий.
            # Различать их незачем: для человека это одно и то же — «такого
            # устройства у вас нет».
            msg = "устройство не найдено"
            raise ServiceError(msg, "device_not_found") from error

        # Кэш гасится сразу, а не по истечении срока: иначе человек нажимает
        # кнопку и ещё минуту видит удалённое устройство в списке.
        await self._cache.drop(devices_key(user_id))

    async def _context(self, user_id: int) -> tuple[int, int]:
        """Идентификатор в панели и лимит устройств тарифа."""
        user = await self._users.get(user_id)
        subscription = await self._subscriptions.get_for_user(user_id)
        if user is None or user.remnawave_id is None or subscription is None:
            msg = "подписки нет, устройств тоже"
            raise ServiceError(msg, "subscription_missing")

        plan = await self._plans.get(subscription.plan_id)
        # Тариф без строки в базе — расхождение, а не повод падать: список
        # устройств человек всё равно увидит, просто без лимита.
        limit = plan.hwid_device_limit if plan is not None else 0
        return user.remnawave_id, limit

    # Sequence, а не list: имя `list` внутри тела класса занято методом ниже,
    # и аннотация `list[...]` здесь означала бы «метод», а не встроенный тип.
    async def _cached(self, user_id: int, panel_id: int) -> Sequence[dict[str, Any]]:
        key = devices_key(user_id)
        stored = await self._cache.get(key)
        if isinstance(stored, list):
            return stored

        # mode="json": в кэш уходит то, что переживёт сериализацию, — даты
        # моделей панели иначе не легли бы в JSON.
        fresh = [device.model_dump(mode="json") for device in await self._panel.list(panel_id)]
        await self._cache.put(key, fresh)
        return fresh


def _view(item: dict[str, Any]) -> DeviceView:
    """Устройство панели в том виде, в каком его показывают человеку.

    Разбор идёт из словаря, а не из модели панели: значение приходит либо
    свежим из фасада, либо из кэша, и вторая ветка знает только JSON.
    """
    return DeviceView(
        hwid=str(item["hwid"]),
        platform=item.get("platform"),
        device_model=item.get("deviceModel"),
        os_version=item.get("osVersion"),
        created_at=datetime.fromisoformat(str(item["createdAt"])),
    )
