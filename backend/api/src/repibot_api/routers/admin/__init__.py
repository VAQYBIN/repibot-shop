"""Административные маршруты, разложенные по предметам.

Одним файлом они занимали 772 строки и семь несвязанных тем: тарифы ничего
не знают о рассылках, а рассылки — об обращениях. Пакет разделяет их по
предмету, оставляя адреса на месте.

Порядок включения повторяет прежний порядок маршрутов в файле: схема OpenAPI
перечисляет пути в порядке объявления, и перестановка сдвинула бы
сгенерированный клиент без единого изменения по существу.

Роль support не допускается ни к тарифам, ни к подпискам, ни к рассылкам:
поддержка разбирается с обращениями, а не с ценообразованием, чужим сроком и
письмами всей базе. Гейт стоит на каждом маршруте отдельно — скрытая кнопка в
интерфейсе защитой не является.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from repibot_api.deps import AuthContext, require_role
from repibot_api.routers.admin import broadcasts, catalog, metrics, nodes, orders, tickets, users
from repibot_core.db.models import UserRole

router = APIRouter(prefix="/api/admin", tags=["admin"])


class WhoAmIResponse(BaseModel):
    id: int
    role: str


# Кто вошёл. Относится ко всей админке, а не к одному предмету, поэтому живёт
# в корне пакета. Пояснение — комментарием, а не строкой документации: она
# уехала бы в описание маршрута в схеме OpenAPI, которой этот переезд менять
# не должен.
@router.get("/whoami", response_model=WhoAmIResponse)
async def whoami(
    context: Annotated[AuthContext, Depends(require_role(UserRole.admin, UserRole.support))],
) -> WhoAmIResponse:
    return WhoAmIResponse(id=context.principal.user_id, role=context.principal.role.value)


router.include_router(catalog.router)
router.include_router(orders.router)
router.include_router(broadcasts.router)
router.include_router(tickets.router)
# Новые предметы включаются после прежних: порядок объявления определяет
# порядок путей в схеме, и дописывать их в конец безопаснее всего.
router.include_router(users.router)
router.include_router(metrics.router)
router.include_router(nodes.router)
