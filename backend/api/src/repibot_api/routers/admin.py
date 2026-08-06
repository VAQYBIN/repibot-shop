"""Административные маршруты: гейт роли и управление тарифами.

Роль support сюда не допускается ни к одному маршруту тарифов: поддержка
разбирается с обращениями, а не с ценообразованием. Гейт стоит на каждом
маршруте отдельно — скрытая кнопка в интерфейсе защитой не является.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import AuthContext, db_session, require_role
from repibot_api.errors import ApiError, api_error_from_service
from repibot_api.schemas import PlanRequest, PlanResponse, SquadResponse
from repibot_core.db.models import TrafficResetStrategy, UserRole
from repibot_core.integrations.remnawave.client import (
    RemnawaveClient,
    RemnawaveUnavailable,
    create_remnawave_client,
)
from repibot_core.integrations.remnawave.squads import PanelSquads
from repibot_core.services.errors import ServiceError
from repibot_core.services.plans import PlanInput, PlanService, PlanView

router = APIRouter(prefix="/api/admin", tags=["admin"])


class WhoAmIResponse(BaseModel):
    id: int
    role: str


@router.get("/whoami", response_model=WhoAmIResponse)
async def whoami(
    context: Annotated[AuthContext, Depends(require_role(UserRole.admin, UserRole.support))],
) -> WhoAmIResponse:
    return WhoAmIResponse(id=context.principal.user_id, role=context.principal.role.value)


def panel_client() -> RemnawaveClient:
    """Точка подмены в тестах: живой панели в наборе нет."""
    return create_remnawave_client()


async def plan_service(
    session: Annotated[AsyncSession, Depends(db_session)],
) -> AsyncIterator[PlanService]:
    """Сервис тарифов вместе с клиентом панели.

    Клиент закрывается после ответа: httpx держит пул соединений, и клиент на
    каждый запрос без закрытия оставляет сокеты открытыми до сборки мусора.
    """
    client = panel_client()
    try:
        yield PlanService(session, PanelSquads(client))
    finally:
        await client.aclose()


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(
    plans: Annotated[PlanService, Depends(plan_service)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> list[PlanResponse]:
    """Все тарифы, включая скрытые и архивные: админ управляет и ими тоже."""
    return [_plan_response(plan) for plan in await plans.all()]


@router.post("/plans", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: PlanRequest,
    plans: Annotated[PlanService, Depends(plan_service)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> PlanResponse:
    try:
        created = await plans.create(_plan_input(payload))
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except RemnawaveUnavailable as error:
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error
    return _plan_response(created)


@router.patch("/plans/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: int,
    payload: PlanRequest,
    plans: Annotated[PlanService, Depends(plan_service)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> PlanResponse:
    try:
        updated = await plans.update(plan_id, _plan_input(payload))
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except RemnawaveUnavailable as error:
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error
    return _plan_response(updated)


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_plan(
    plan_id: int,
    plans: Annotated[PlanService, Depends(plan_service)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> None:
    """Архивация, а не удаление: на тариф ссылаются подписки и журнал."""
    try:
        await plans.archive(plan_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error


@router.get("/remnawave/squads", response_model=list[SquadResponse])
async def list_squads(
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> list[SquadResponse]:
    """Сквады читаются из панели, а не хранятся у нас: их состав меняет админ панели."""
    client = panel_client()
    try:
        squads = await PanelSquads(client).list()
    except RemnawaveUnavailable as error:
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error
    finally:
        await client.aclose()
    return [SquadResponse(uuid=squad.uuid, name=squad.name) for squad in squads]


def _plan_input(payload: PlanRequest) -> PlanInput:
    return PlanInput(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        duration_days=payload.duration_days,
        price_rub=payload.price_rub,
        price_stars=payload.price_stars,
        traffic_limit_bytes=payload.traffic_limit_bytes,
        traffic_reset_strategy=TrafficResetStrategy(payload.traffic_reset_strategy),
        hwid_device_limit=payload.hwid_device_limit,
        # В базе колонка строковая: ARRAY(UUID) с as_uuid=False, и объекты UUID
        # туда не уедут.
        internal_squad_uuids=[str(uuid) for uuid in payload.internal_squad_uuids],
        is_trial=payload.is_trial,
        is_visible=payload.is_visible,
        sort_order=payload.sort_order,
    )


def _plan_response(plan: PlanView) -> PlanResponse:
    return PlanResponse(
        id=plan.id,
        code=plan.code,
        name=plan.name,
        description=plan.description,
        duration_days=plan.duration_days,
        price_rub=plan.price_rub,
        price_stars=plan.price_stars,
        traffic_limit_bytes=plan.traffic_limit_bytes,
        traffic_reset_strategy=plan.traffic_reset_strategy.value,
        hwid_device_limit=plan.hwid_device_limit,
        internal_squad_uuids=[UUID(uuid) for uuid in plan.internal_squad_uuids],
        is_trial=plan.is_trial,
        is_active=plan.is_active,
        is_visible=plan.is_visible,
        sort_order=plan.sort_order,
    )
