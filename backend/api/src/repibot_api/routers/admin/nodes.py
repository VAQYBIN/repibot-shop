"""Ноды панели в админке: только просмотр состояния узлов.

Схема ответа объявлена здесь, а не в общем schemas.py: соседние предметы
админки наполняются одновременно, и общий файл стал бы местом столкновения.
Прецедент — WhoAmIResponse в корне пакета.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from repibot_api.deps import AuthContext, require_role
from repibot_api.errors import ApiError
from repibot_api.subscription_view import panel_client
from repibot_core.db.models import UserRole
from repibot_core.integrations.remnawave.client import RemnawaveError
from repibot_core.integrations.remnawave.nodes import PanelNodes
from repibot_core.integrations.remnawave.types import PanelNode

# Без префикса: он стоит на общем роутере пакета.
router = APIRouter()


class NodeResponse(BaseModel):
    """Ровно то, что показывает экран узлов.

    Ответ панели несёт ссылку на прокси с паролем, ключи Reality внутри
    инбаундов и внутренние идентификаторы узла и профиля конфигурации.
    Пробросить его целиком — значит отдать всё это браузеру администратора,
    поэтому поля перечислены поимённо, а не скопированы.
    """

    name: str
    country_code: str
    address: str
    # Порт панель отдаёт необязательным: у ноды за прокси его нет.
    port: int | None
    is_connected: bool
    is_disabled: bool
    users_online: int
    traffic_used_bytes: int
    # Ноль — «без лимита»: панель обозначает отсутствие ограничения и нулём, и
    # пустым значением, и различать их на экране незачем.
    traffic_limit_bytes: int
    xray_uptime_seconds: int
    last_status_message: str | None


@router.get("/nodes", response_model=list[NodeResponse])
async def list_nodes(
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> list[NodeResponse]:
    """Узлы читаются из панели: своей копии их состояния у нас нет и быть не должно."""
    client = panel_client()
    try:
        nodes = await PanelNodes(client).list()
    except RemnawaveError as error:
        # И молчание, и отказ панели одинаковы для администратора: списка нет
        # не по его вине, и повторить попытку — единственное, что он сделает.
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error
    finally:
        await client.aclose()
    return [_node_response(node) for node in nodes]


def _node_response(node: PanelNode) -> NodeResponse:
    # Числа панель отдаёт с плавающей точкой — байты и секунды в ответе API
    # целые: дробный байт ничего не значит и только мешает читать.
    return NodeResponse(
        name=node.name,
        country_code=node.countryCode,
        address=node.address,
        port=int(node.port) if node.port is not None else None,
        is_connected=node.isConnected,
        is_disabled=node.isDisabled,
        users_online=int(node.usersOnline),
        traffic_used_bytes=int(node.trafficUsedBytes or 0),
        traffic_limit_bytes=int(node.trafficLimitBytes or 0),
        xray_uptime_seconds=int(node.xrayUptime),
        last_status_message=node.lastStatusMessage,
    )
