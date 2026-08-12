"""Панель Remnawave 3.2.1 в памяти.

Подменяется транспорт, а не фасад: маршруты, методы и тела запросов при этом
проверяются настоящие. Заглушка повторяет форму ответов и правила поиска, но
не поведение живой панели — ручная проверка остаётся обязательной.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from repibot_core.integrations.remnawave.client import RemnawaveClient

BASE_URL = "https://panel.example.test"


class FakePanel:
    def __init__(self) -> None:
        self.users: dict[int, dict[str, Any]] = {}
        self.squads: list[dict[str, Any]] = []
        self.devices: dict[int, list[dict[str, Any]]] = {}
        # Трафик хранится днями: панель отдаёт его как ряд по датам, а не
        # одним числом, и тесты сверяют именно разбивку.
        self.usage: dict[int, dict[str, float]] = {}
        self.requests: list[tuple[str, str]] = []
        # Строка запроса последнего вызова: обязательные start и end иначе
        # никак не проверить — в путь они не попадают.
        self.last_query: dict[str, str] = {}
        self._next_id = 1
        self._failures = 0

    # --- сборка ---

    def client(self) -> RemnawaveClient:
        # Одна попытка: тесту, проверяющему отказ, незачем ждать три захода
        # с экспоненциальной задержкой.
        return RemnawaveClient(
            base_url=BASE_URL,
            token="test",  # noqa: S106 — панели за транспортом нет, токен ни к чему не подходит
            max_attempts=1,
            transport=self.transport(),
        )

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def add_squad(self, uuid: str, name: str) -> None:
        self.squads.append(
            {
                "uuid": uuid,
                "viewPosition": len(self.squads),
                "name": name,
                "info": {"membersCount": 0, "inboundsCount": 0},
                "inbounds": [],
                "createdAt": _now(),
                "updatedAt": _now(),
            }
        )

    def add_device(
        self,
        panel_id: int,
        hwid: str,
        *,
        platform: str | None = None,
        os_version: str | None = None,
        device_model: str | None = None,
    ) -> None:
        self.devices.setdefault(panel_id, []).append(
            {
                "hwid": hwid,
                "userId": panel_id,
                "platform": platform,
                "osVersion": os_version,
                "deviceModel": device_model,
                "userAgent": None,
                "requestIp": None,
                "createdAt": _now(),
                "updatedAt": _now(),
            }
        )

    def add_usage(self, panel_id: int, day: str, used_bytes: float) -> None:
        self.usage.setdefault(panel_id, {})[day] = used_bytes

    def fail_next(self, times: int = 1) -> None:
        """Следующие запросы отвечают 503 — панель «лежит»."""
        self._failures = times

    # --- обработка ---

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, request.url.path))
        self.last_query = dict(request.url.params)

        if self._failures > 0:
            self._failures -= 1
            return httpx.Response(503, json={"message": "panel is down"})

        path = request.url.path
        if path == "/api/internal-squads":
            return httpx.Response(
                200, json={"response": {"total": len(self.squads), "internalSquads": self.squads}}
            )
        if path == "/api/nodes":
            # Заглушка не заводит узлов: сквозной стек проверяет админку без
            # настоящей панели, и пустой список — честный ответ «узлов нет»,
            # а не притворство, что маршрут не существует.
            return httpx.Response(200, json={"response": []})
        if path == "/api/users" and request.method == "POST":
            return self._create(json.loads(request.content))
        if path == "/api/users" and request.method == "PATCH":
            return self._update(json.loads(request.content))
        if path == "/api/users/resolve":
            return self._resolve(json.loads(request.content))
        if path.startswith("/api/users/"):
            tail = path.rsplit("/", 1)[-1]
            # Нечисловой хвост — не пользователь, а незнакомый маршрут.
            # Панель на такое отвечает 404, а не падает.
            if tail.isdigit():
                return self._get(int(tail))
        # Удаление проверяется раньше списка: у обоих маршрутов общий префикс
        # /api/hwid/devices/, и хвост «delete» иначе разбирался бы как номер
        # пользователя.
        if path == "/api/hwid/devices/delete" and request.method == "POST":
            return self._delete_device(json.loads(request.content))
        if path.startswith("/api/hwid/devices/") and request.method == "GET":
            return self._devices(int(path.rsplit("/", 1)[-1]))
        if path.startswith("/api/bandwidth-stats/users/"):
            return self._usage(int(path.rsplit("/", 1)[-1]))

        return httpx.Response(404, json={"message": "not found"})

    def _create(self, body: dict[str, Any]) -> httpx.Response:
        if any(user["username"] == body["username"] for user in self.users.values()):
            return httpx.Response(400, json={"message": "username already exists"})

        panel_id = self._next_id
        self._next_id += 1
        short_uuid = uuid4().hex[:16]
        user = _template(panel_id, short_uuid, body)
        self.users[panel_id] = user
        return httpx.Response(200, json={"response": user})

    def _update(self, body: dict[str, Any]) -> httpx.Response:
        # Фасад шлёт только явно заданные поля, поэтому заданное мержится в
        # хранимого пользователя. Замена целиком стирала бы всё, чего в PATCH
        # не было, — панель так себя не ведёт.
        # Идентификатор в схеме 3.2.1 объявлен числом, и в JSON приходит как
        # 42.0: без int() ключ словаря не совпадёт.
        user = self.users.get(int(body["id"]))
        if user is None:
            return httpx.Response(404, json={"message": "not found"})
        for key, value in body.items():
            if key == "id":
                continue
            user[key] = _squads(value) if key == "activeInternalSquads" else value
        user["updatedAt"] = _now()
        return httpx.Response(200, json={"response": user})

    def _resolve(self, body: dict[str, Any]) -> httpx.Response:
        # В теле ровно один ключ: фасад отбрасывает незаданные.
        for user in self.users.values():
            if "id" in body and user["id"] == int(body["id"]):
                return httpx.Response(200, json={"response": user})
            if "shortUuid" in body and user["shortUuid"] == body["shortUuid"]:
                return httpx.Response(200, json={"response": user})
            if "username" in body and user["username"] == body["username"]:
                return httpx.Response(200, json={"response": user})
        return httpx.Response(404, json={"message": "not found"})

    def _get(self, panel_id: int) -> httpx.Response:
        user = self.users.get(panel_id)
        if user is None:
            return httpx.Response(404, json={"message": "not found"})
        return httpx.Response(200, json={"response": user})

    def _devices(self, panel_id: int) -> httpx.Response:
        devices = self.devices.get(panel_id, [])
        return httpx.Response(200, json={"response": {"total": len(devices), "devices": devices}})

    def _delete_device(self, body: dict[str, Any]) -> httpx.Response:
        # int: идентификатор в схеме объявлен числом и приходит как 7.0.
        panel_id = int(body["userId"])
        devices = self.devices.get(panel_id, [])
        remaining = [device for device in devices if device["hwid"] != body["hwid"]]
        if len(remaining) == len(devices):
            # Панель отвечает отказом на чужой или несуществующий hwid — от
            # этого зависит поведение сервиса, и заглушка обязана его повторять.
            return httpx.Response(404, json={"message": "device not found"})
        self.devices[panel_id] = remaining
        return httpx.Response(200, json={"response": {"isDeleted": True}})

    def _usage(self, panel_id: int) -> httpx.Response:
        days = self.usage.get(panel_id, {})
        categories = sorted(days)
        return httpx.Response(
            200,
            json={
                "response": {
                    "categories": categories,
                    "sparklineData": [days[day] for day in categories],
                    "topNodes": [],
                    # Без единого дня ряд пустой: панель не рисует ноду, по
                    # которой ничего не прошло.
                    "series": [
                        {
                            "uuid": "22222222-2222-4222-8222-222222222222",
                            "name": "Нода",
                            "color": "#000000",
                            "countryCode": "NL",
                            "total": sum(days.values()),
                            "data": [days[day] for day in categories],
                        }
                    ]
                    if categories
                    else [],
                }
            },
        )


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _squads(uuids: Any) -> list[dict[str, str]]:
    """Сквады в запросе — список uuid, в ответе — объекты с именем.

    Имя заглушка не знает и подставляет uuid: тесты сверяют состав, а не
    подписи. Без этого превращения ответ не разобрался бы моделью.
    """
    return [{"uuid": str(uuid), "name": str(uuid)} for uuid in uuids or []]


def _template(panel_id: int, short_uuid: str, body: dict[str, Any]) -> dict[str, Any]:
    """Пользователь панели со всеми обязательными полями ответа."""
    return {
        "id": panel_id,
        "shortUuid": short_uuid,
        "username": body["username"],
        "status": body.get("status", "ACTIVE"),
        "trafficLimitBytes": body.get("trafficLimitBytes", 0),
        "trafficLimitStrategy": body.get("trafficLimitStrategy", "NO_RESET"),
        "expireAt": body["expireAt"],
        "telegramId": body.get("telegramId"),
        "email": body.get("email"),
        "description": body.get("description"),
        "tag": body.get("tag"),
        "hwidDeviceLimit": body.get("hwidDeviceLimit", 0),
        "externalSquadUuid": body.get("externalSquadUuid"),
        "trojanPassword": "trojan-password",
        "vlessUuid": str(uuid4()),
        "ssPassword": "ss-password",
        "lastTriggeredThreshold": 0,
        "subRevokedAt": None,
        "lastTrafficResetAt": None,
        "createdAt": _now(),
        "updatedAt": _now(),
        "subscriptionUrl": f"{BASE_URL}/sub/{short_uuid}",
        "activeInternalSquads": _squads(body.get("activeInternalSquads")),
        "userTraffic": {
            "usedTrafficBytes": 0,
            "lifetimeUsedTrafficBytes": 0,
            "onlineAt": _now(),
            "firstConnectedAt": _now(),
            "lastConnectedNodeUuid": str(uuid4()),
        },
    }
