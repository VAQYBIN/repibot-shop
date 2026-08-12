"""Пользователи панели.

Фасад знает адреса и формы запросов, но не знает, зачем их зовут. Решение
«создать или обновить» принимает сервис примирения.
"""

from __future__ import annotations

import httpx

from repibot_core.integrations.remnawave.client import RemnawaveClient, RemnawaveRejected
from repibot_core.integrations.remnawave.models import UserResponseDto
from repibot_core.integrations.remnawave.types import (
    CreateUserBody,
    PanelUser,
    ResolveUserBody,
    UpdateUserBody,
)


class PanelUsers:
    def __init__(self, client: RemnawaveClient) -> None:
        self._client = client

    async def get(self, panel_id: int) -> PanelUser | None:
        response = await self._client.request("GET", f"/api/users/{panel_id}")
        return self._one_or_none(response)

    async def resolve(
        self,
        *,
        panel_id: int | None = None,
        short_uuid: str | None = None,
        username: str | None = None,
    ) -> PanelUser | None:
        """Поиск пользователя по одному из трёх ключей.

        Заменяет удалённые в 3.2.1 маршруты by-email, by-telegram-id и by-tag.
        Пустые ключи не отправляются: панель различает «не задано» и «пусто».
        """
        body = ResolveUserBody(id=panel_id, shortUuid=short_uuid, username=username)
        response = await self._client.request(
            "POST", "/api/users/resolve", content=body.model_dump_json(exclude_none=True)
        )
        return self._one_or_none(response)

    async def create(self, body: CreateUserBody) -> PanelUser:
        response = await self._client.request(
            "POST", "/api/users", content=body.model_dump_json(exclude_none=True)
        )
        return self._one(response)

    async def update(self, body: UpdateUserBody) -> PanelUser:
        """Частичное обновление: уходит только то, что вызывающий задал явно.

        В 3.2.1 обновление идёт на коллекцию, идентификатор — в теле.

        exclude_unset, а не exclude_none: у trafficLimitStrategy в схеме
        панели значение по умолчанию «NO_RESET», и отбор по None его не
        отсекает. Правка одного лимита устройств тогда молча сбрасывала бы
        пользователю стратегию сброса трафика.
        """
        response = await self._client.request(
            "PATCH", "/api/users", content=body.model_dump_json(exclude_unset=True)
        )
        return self._one(response)

    async def revoke(self, panel_id: int) -> PanelUser:
        """Выпускает новую ссылку подписки взамен прежней.

        Панель меняет shortUuid, то есть старый адрес перестаёт работать на
        всех устройствах человека. Ответ — тот же пользователь целиком, и
        адрес подписки в нём уже новый: собирать его у себя нельзя, публичный
        домен подписки настраивается в панели отдельно.

        Тела у запроса нет: панель определяет, кому выпускать ссылку, по
        номеру в адресе.
        """
        response = await self._client.request("POST", f"/api/users/{panel_id}/actions/revoke")
        return self._one(response)

    @staticmethod
    def _one(response: httpx.Response) -> PanelUser:
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise RemnawaveRejected(response.status_code, response.text[:500])
        return UserResponseDto.model_validate_json(response.content).response

    @classmethod
    def _one_or_none(cls, response: httpx.Response) -> PanelUser | None:
        # 404 — не отказ, а ответ «такого пользователя нет». Ошибкой его
        # делать нельзя: примирение на нём создаёт пользователя.
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        return cls._one(response)
