"""Витрина тарифов и подписка текущего пользователя.

Отдельным файлом, а не дописыванием в me.py: общий файл в подпроекте 1 дважды
становился местом столкновения параллельных задач.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from repibot_api.deps import AuthContext, current_context
from repibot_api.errors import ApiError, api_error_from_service
from repibot_api.schemas import PublicPlanResponse, SubscriptionStateResponse
from repibot_api.subscription_view import (
    plan_service,
    subscription_response,
    subscription_service,
)
from repibot_core.integrations.remnawave.client import RemnawaveUnavailable
from repibot_core.services.errors import ServiceError
from repibot_core.services.plans import PlanService
from repibot_core.services.subscriptions import SubscriptionService

router = APIRouter(tags=["subscription"])


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
        subscription=subscription_response(view) if view is not None else None,
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
    return SubscriptionStateResponse(
        subscription=subscription_response(view), trial_available=False
    )
