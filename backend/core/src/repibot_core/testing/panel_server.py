"""ASGI-сервер над :class:`FakePanel` для изолированного сквозного стека."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from repibot_core.integrations.remnawave.types import CreateUserBody
from repibot_core.testing.remnawave import FakePanel


def create_panel_app() -> Starlette:
    """Создать панель с независимым состоянием.

    Фабрика нужна unit-тестам: модульный ``panel_app`` живёт весь срок процесса
    uvicorn, а два теста не должны видеть пользователей друг друга.
    """
    panel = FakePanel()

    async def seed_user(request: Request) -> Response:
        try:
            raw = await request.json()
            body, device, traffic = _validate_seed(raw)
        except (json.JSONDecodeError, TypeError, ValueError, ValidationError):
            return JSONResponse({"message": "invalid seed payload"}, status_code=400)

        create_request = httpx.Request(
            "POST",
            "http://panel.test/api/users",
            content=body.model_dump_json(exclude_none=True, warnings=False),
        )
        # HTTP-обёртка намеренно вызывает транспортное ядро FakePanel: так сеть
        # и MockTransport используют одну реализацию маршрутов.
        created = panel._handle(create_request)
        if created.status_code >= 400:
            return _response(created)

        user = created.json()["response"]
        panel_id = int(user["id"])
        if device is not None:
            panel.add_device(
                panel_id,
                device["hwid"] or "",
                platform=device["platform"],
                os_version=device["os_version"],
                device_model=device["device_model"],
            )
        if traffic is not None:
            user_traffic = user["userTraffic"]
            user_traffic["usedTrafficBytes"] = traffic["usedTrafficBytes"]
            user_traffic["lifetimeUsedTrafficBytes"] = traffic["lifetimeUsedTrafficBytes"]
            for day, used_bytes in traffic["days"].items():
                panel.add_usage(panel_id, day, used_bytes)
        return JSONResponse({"response": user}, status_code=201)

    async def proxy(request: Request) -> Response:
        upstream = httpx.Request(
            request.method,
            str(request.url),
            headers=request.headers.raw,
            content=await request.body(),
        )
        return _response(panel._handle(upstream))

    async def health(_: Request) -> Response:
        return JSONResponse({"status": "ok"})

    app = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/__seed/user", seed_user, methods=["POST"]),
            Route("/{path:path}", proxy, methods=["GET", "POST", "PATCH", "DELETE"]),
        ]
    )
    app.state.panel = panel
    return app


def _validate_seed(
    raw: Any,
) -> tuple[CreateUserBody, dict[str, str | None] | None, dict[str, Any] | None]:
    if not isinstance(raw, dict):
        raise TypeError

    create_fields = {key: value for key, value in raw.items() if key not in {"device", "traffic"}}
    body = CreateUserBody.model_validate(create_fields)

    device_raw = raw.get("device")
    device: dict[str, str | None] | None = None
    if device_raw is not None:
        if not isinstance(device_raw, dict):
            raise TypeError
        hwid = device_raw.get("hwid")
        if not isinstance(hwid, str) or not hwid:
            raise ValueError
        device = {
            "hwid": hwid,
            "platform": _optional_string(device_raw, "platform"),
            "os_version": _optional_string(device_raw, "osVersion"),
            "device_model": _optional_string(device_raw, "deviceModel"),
        }

    traffic_raw = raw.get("traffic")
    traffic: dict[str, Any] | None = None
    if traffic_raw is not None:
        if not isinstance(traffic_raw, dict):
            raise TypeError
        days_raw = traffic_raw.get("days", {})
        if not isinstance(days_raw, dict):
            raise TypeError
        days: dict[str, float] = {}
        for raw_day, raw_bytes in days_raw.items():
            if not isinstance(raw_day, str):
                raise TypeError
            date.fromisoformat(raw_day)
            days[raw_day] = _non_negative_number(raw_bytes)
        traffic = {
            "usedTrafficBytes": _non_negative_number(traffic_raw.get("usedTrafficBytes", 0)),
            "lifetimeUsedTrafficBytes": _non_negative_number(
                traffic_raw.get("lifetimeUsedTrafficBytes", 0)
            ),
            "days": days,
        }
    return body, device, traffic


def _optional_string(values: dict[str, Any], key: str) -> str | None:
    value = values.get(key)
    if value is not None and not isinstance(value, str):
        raise TypeError
    return value


def _non_negative_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise ValueError
    return float(value)


def _response(response: httpx.Response) -> Response:
    return Response(
        response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json"),
    )


panel_app = create_panel_app()

__all__ = ["create_panel_app", "panel_app"]
