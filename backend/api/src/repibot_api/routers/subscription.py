"""Витрина тарифов и подписка текущего пользователя.

Отдельным файлом, а не дописыванием в me.py: общий файл в подпроекте 1 дважды
становился местом столкновения параллельных задач.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import AuthContext, current_context, db_session
from repibot_api.errors import ApiError, api_error_from_service
from repibot_api.schemas import (
    PublicPlanResponse,
    SubscriptionResponse,
    SubscriptionStateResponse,
)
from repibot_core.integrations.remnawave.client import (
    RemnawaveClient,
    RemnawaveUnavailable,
    create_remnawave_client,
)
from repibot_core.integrations.remnawave.squads import PanelSquads
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.errors import ServiceError
from repibot_core.services.plans import PlanService
from repibot_core.services.provisioning import ProvisioningService
from repibot_core.services.subscriptions import SubscriptionService, SubscriptionView
from repibot_core.settings import get_settings

router = APIRouter(tags=["subscription"])


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


async def subscription_service(
    session: Annotated[AsyncSession, Depends(db_session)],
) -> AsyncIterator[SubscriptionService]:
    """Сервис подписки вместе с клиентом панели.

    Клиент нужен здесь по-настоящему: активация триала сразу же пробует завести
    пользователя в панели. Закрывается он так же, как у тарифов, — в finally.
    """
    client = panel_client()
    try:
        yield SubscriptionService(
            session, get_settings(), ProvisioningService(session, PanelUsers(client))
        )
    finally:
        await client.aclose()


@router.get("/api/plans", response_model=list[PublicPlanResponse])
async def list_plans(
    plans: Annotated[PlanService, Depends(plan_service)],
) -> list[PublicPlanResponse]:
    """Витрина открыта без входа: до регистрации человеку не на что смотреть."""
    return [
        PublicPlanResponse(
            id=plan.id,
            code=plan.code,
            name=plan.name,
            description=plan.description,
            duration_days=plan.duration_days,
            price_rub=plan.price_rub,
            price_stars=plan.price_stars,
            traffic_limit_bytes=plan.traffic_limit_bytes,
            hwid_device_limit=plan.hwid_device_limit,
            is_trial=plan.is_trial,
        )
        for plan in await plans.visible()
    ]


@router.get("/api/me/subscription", response_model=SubscriptionStateResponse)
async def my_subscription(
    subscriptions: Annotated[SubscriptionService, Depends(subscription_service)],
    context: Annotated[AuthContext, Depends(current_context)],
) -> SubscriptionStateResponse:
    """Подписки может не быть, и это не ошибка.

    Пустой ответ со статусом 200 фронтенд отличает от отказа; 404 он вынужден
    был бы разбирать по коду, чтобы понять, показывать витрину или сообщение.
    """
    view = await subscriptions.current(context.principal.user_id)
    return SubscriptionStateResponse(
        subscription=_response(view) if view is not None else None,
        trial_available=await subscriptions.trial_available(context.principal.user_id),
    )


@router.post(
    "/api/me/subscription/trial",
    response_model=SubscriptionStateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def activate_trial(
    subscriptions: Annotated[SubscriptionService, Depends(subscription_service)],
    context: Annotated[AuthContext, Depends(current_context)],
) -> SubscriptionStateResponse:
    try:
        view = await subscriptions.activate_trial(context.principal.user_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except RemnawaveUnavailable as error:  # pragma: no cover — выдача уходит в очередь
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error
    # Право на триал израсходовано в той же транзакции, что и подписка:
    # перечитывать его из базы значит задать вопрос с известным ответом.
    return SubscriptionStateResponse(subscription=_response(view), trial_available=False)


def _response(view: SubscriptionView) -> SubscriptionResponse:
    return SubscriptionResponse(
        plan_code=view.plan_code,
        plan_name=view.plan_name,
        status=view.status.value,
        started_at=view.started_at,
        expires_at=view.expires_at,
        subscription_url=view.subscription_url,
        traffic_limit_bytes=view.traffic_limit_bytes,
        hwid_device_limit=view.hwid_device_limit,
    )
