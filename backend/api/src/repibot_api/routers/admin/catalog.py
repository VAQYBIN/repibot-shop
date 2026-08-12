"""Каталог: промокоды, тарифы и сквады панели.

Один предмет — то, что администратор продаёт. Тариф собирается из сквадов
панели, промокод меняет его цену, поэтому все трое живут рядом. Роль support
сюда не допускается: поддержка разбирается с обращениями, а не с
ценообразованием.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import AuthContext, db_session, require_role
from repibot_api.errors import ApiError, api_error_from_service
from repibot_api.schemas import (
    PlanRequest,
    PlanResponse,
    PromoRequest,
    PromoResponse,
    SquadResponse,
)
from repibot_api.subscription_view import panel_client, plan_service
from repibot_core.db.models import TrafficResetStrategy, UserRole
from repibot_core.integrations.remnawave.client import RemnawaveUnavailable
from repibot_core.integrations.remnawave.squads import PanelSquads
from repibot_core.services.errors import ServiceError
from repibot_core.services.plans import PlanInput, PlanService, PlanView
from repibot_core.services.promotions import PromotionInput, PromotionService

# Без префикса и меток: и то и другое стоит на общем роутере пакета, иначе
# адреса маршрутов уехали бы вместе с переездом файла.
router = APIRouter()


@router.get("/promos", response_model=list[PromoResponse])
async def list_promos(
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> list[PromoResponse]:
    return [_promo_response(item) for item in await PromotionService(session).list()]


@router.post("/promos", response_model=PromoResponse, status_code=status.HTTP_201_CREATED)
async def create_promo(
    payload: PromoRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> PromoResponse:
    try:
        item = await PromotionService(session).create(_promo_input(payload))
        await session.commit()
    except ServiceError as error:
        raise api_error_from_service(error) from error
    return _promo_response(item)


@router.patch("/promos/{promo_id}", response_model=PromoResponse)
async def update_promo(
    promo_id: int,
    payload: PromoRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> PromoResponse:
    try:
        item = await PromotionService(session).update(promo_id, _promo_input(payload))
        await session.commit()
    except ServiceError as error:
        raise api_error_from_service(error) from error
    return _promo_response(item)


@router.delete("/promos/{promo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_promo(
    promo_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> None:
    try:
        await PromotionService(session).deactivate(promo_id)
        await session.commit()
    except ServiceError as error:
        raise api_error_from_service(error) from error


def _promo_input(payload: PromoRequest) -> PromotionInput:
    return PromotionInput(**payload.model_dump())


def _promo_response(item: object) -> PromoResponse:
    return PromoResponse.model_validate(item, from_attributes=True)


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
