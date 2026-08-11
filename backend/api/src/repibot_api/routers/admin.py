"""Административные маршруты: гейт роли, тарифы, начисление дней, рассылки.

Роль support не допускается ни к одному маршруту тарифов, подписок и рассылок:
поддержка разбирается с обращениями, а не с ценообразованием, чужим сроком и
письмами всей базе. Обращения — единственное, что ей открыто, и открыто вместе
с администратором. Гейт стоит на каждом маршруте отдельно — скрытая кнопка в
интерфейсе защитой не является.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import AuthContext, client_ip, db_session, require_role
from repibot_api.errors import ApiError, api_error_from_service
from repibot_api.schemas import (
    AdminSubscriptionRequest,
    AdminTicketResponse,
    AdminTicketThreadResponse,
    BroadcastResponse,
    CompensationRequest,
    CreateBroadcastRequest,
    PlanRequest,
    PlanResponse,
    PromoRequest,
    PromoResponse,
    RefundMarkRequest,
    SegmentCountResponse,
    SquadResponse,
    SubscriptionStateResponse,
    TicketMessageResponse,
    TicketReplyRequest,
)
from repibot_api.subscription_view import (
    panel_client,
    plan_service,
    subscription_response,
    subscription_service,
)
from repibot_core.db.models import (
    Broadcast,
    Order,
    OrderStatus,
    Plan,
    ReferralReward,
    Subscription,
    SubscriptionActor,
    SubscriptionEventType,
    SubscriptionSource,
    Ticket,
    TicketMessage,
    TicketStatus,
    TrafficResetStrategy,
    UserRole,
)
from repibot_core.db.repositories.audit import AuditRepository
from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.integrations.remnawave.client import RemnawaveUnavailable
from repibot_core.integrations.remnawave.squads import PanelSquads
from repibot_core.services.broadcasts import BroadcastService
from repibot_core.services.errors import ServiceError
from repibot_core.services.plans import PlanInput, PlanService, PlanView
from repibot_core.services.promotions import PromotionInput, PromotionService
from repibot_core.services.provisioning import TOPIC_PROVISION
from repibot_core.services.segments import count_segment
from repibot_core.services.subscriptions import SubscriptionService, SubscriptionView
from repibot_core.services.support import SupportService

router = APIRouter(prefix="/api/admin", tags=["admin"])


class WhoAmIResponse(BaseModel):
    id: int
    role: str


@router.get("/whoami", response_model=WhoAmIResponse)
async def whoami(
    context: Annotated[AuthContext, Depends(require_role(UserRole.admin, UserRole.support))],
) -> WhoAmIResponse:
    return WhoAmIResponse(id=context.principal.user_id, role=context.principal.role.value)


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


@router.post("/users/{user_id}/subscription", response_model=SubscriptionStateResponse)
async def grant_subscription(
    user_id: int,
    payload: AdminSubscriptionRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
    plans: Annotated[PlanService, Depends(plan_service)],
    subscriptions: Annotated[SubscriptionService, Depends(subscription_service)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
    ip: Annotated[str | None, Depends(client_ip)],
) -> SubscriptionStateResponse:
    """Начисление дней и смена тарифа руками админа.

    Тело без days означает смену тарифа с конвертацией оплаченного остатка, с
    days — начисление указанного числа дней по этому тарифу. Разные действия
    разными полями, а не двумя маршрутами: решение принимает один и тот же
    человек в одной и той же форме.
    """
    before = await subscriptions.current(user_id)
    try:
        plan = await plans.require(payload.plan_id)
        if payload.days is None:
            view = await subscriptions.change_plan(
                user_id,
                payload.plan_id,
                actor=SubscriptionActor.admin,
                actor_user_id=context.principal.user_id,
            )
        else:
            view = await subscriptions.grant_days(
                user_id,
                plan,
                payload.days,
                source=SubscriptionSource.admin,
                event_type=SubscriptionEventType.admin_grant,
                actor=SubscriptionActor.admin,
                actor_user_id=context.principal.user_id,
                comment=payload.comment,
            )
    except ServiceError as error:
        raise api_error_from_service(error) from error

    # Каждое действие персонала оставляет след с состоянием до и после:
    # спор «кому и сколько начислили» иначе не разобрать.
    await AuditRepository(session).record(
        "subscription.grant",
        "subscription",
        actor_id=context.principal.user_id,
        entity_id=str(user_id),
        before=_audit_snapshot(before),
        after=_audit_snapshot(view),
        ip=ip,
    )
    await session.commit()

    # Право на триал здесь не считается: админ смотрит на подписку, которую
    # только что завёл, и триал ей уже не положен.
    return SubscriptionStateResponse(
        subscription=subscription_response(view), trial_available=False
    )


@router.post("/orders/{order_id}/refund-mark", status_code=status.HTTP_204_NO_CONTENT)
async def mark_order_refunded(
    order_id: int,
    payload: RefundMarkRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
    ip: Annotated[str | None, Depends(client_ip)],
) -> None:
    """Фиксирует выполненный у провайдера возврат, не трогая выданный доступ."""
    try:
        if session.in_transaction():
            await session.commit()
        async with session.begin():
            order = await _locked_order(session, order_id)
            if order.status not in (OrderStatus.fulfilled, OrderStatus.refunded):
                raise ServiceError(
                    "возврат можно отметить только для оплаченного заказа", "refund_invalid"
                )
            if order.status is OrderStatus.refunded:
                return
            before = _order_snapshot(order)
            order.status = OrderStatus.refunded
            await AuditRepository(session).record(
                "order.refund_mark",
                "order",
                actor_id=context.principal.user_id,
                entity_id=str(order.id),
                before=before,
                after={
                    **_order_snapshot(order),
                    "reference": payload.reference,
                    "comment": payload.comment,
                },
                ip=ip,
            )
    except ServiceError as error:
        raise api_error_from_service(error) from error


@router.post("/orders/{order_id}/compensations", status_code=status.HTTP_204_NO_CONTENT)
async def compensate_order(
    order_id: int,
    payload: CompensationRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
    ip: Annotated[str | None, Depends(client_ip)],
) -> None:
    """Применяет ровно одну названную и идемпотентную местную коррекцию."""
    try:
        if session.in_transaction():
            await session.commit()
        async with session.begin():
            order = await _locked_order(session, order_id)
            audits = AuditRepository(session)
            if await audits.compensation_with_key(order.id, payload.idempotency_key) is not None:
                return
            if await audits.compensation_for_action(order.id, payload.action) is not None:
                raise ServiceError("эта компенсация уже применена", "compensation_already_applied")
            if order.status not in (OrderStatus.fulfilled, OrderStatus.refunded):
                raise ServiceError("компенсация требует оплаченный заказ", "compensation_invalid")

            if payload.action == "revoke_days":
                before, after = await _revoke_days(
                    session,
                    user_id=order.user_id,
                    days=order.duration_days_snapshot,
                    actor_id=context.principal.user_id,
                    comment=payload.comment,
                )
            else:
                reward = await session.scalar(
                    select(ReferralReward)
                    .where(ReferralReward.origin_order_id == order.id)
                    .with_for_update()
                )
                if reward is None or reward.reversed_at is not None:
                    raise ServiceError(
                        "реферальную награду уже нельзя сторнировать", "reward_missing"
                    )
                reward_before = _reward_snapshot(reward)
                before, after = await _revoke_days(
                    session,
                    user_id=reward.referrer_user_id,
                    days=reward.days,
                    actor_id=context.principal.user_id,
                    comment=payload.comment,
                )
                reward.reversed_at = datetime.now(UTC)
                before["referral_reward"] = reward_before
                after["referral_reward"] = _reward_snapshot(reward)

            await audits.record(
                "order.compensation",
                "order",
                actor_id=context.principal.user_id,
                entity_id=str(order.id),
                before=before,
                after={
                    **after,
                    "action": payload.action,
                    "idempotency_key": payload.idempotency_key,
                    "comment": payload.comment,
                },
                ip=ip,
            )
    except ServiceError as error:
        raise api_error_from_service(error) from error


async def _locked_order(session: AsyncSession, order_id: int) -> Order:
    order = await session.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if order is None:
        raise ServiceError("заказ не найден", "order_not_found")
    return order


def _order_snapshot(order: Order) -> dict[str, object]:
    return {"status": order.status.value, "duration_days": order.duration_days_snapshot}


def _reward_snapshot(reward: ReferralReward) -> dict[str, object]:
    return {
        "id": reward.id,
        "origin_order_id": reward.origin_order_id,
        "days": reward.days,
        "reversed_at": (None if reward.reversed_at is None else reward.reversed_at.isoformat()),
    }


async def _revoke_days(
    session: AsyncSession,
    *,
    user_id: int,
    days: int,
    actor_id: int,
    comment: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Снимает дни, пишет событие и ставит примирение с панелью в очередь."""
    subscriptions = SubscriptionRepository(session)
    await subscriptions.lock_user_for_entitlement(user_id)
    subscription = await subscriptions.get_for_user_for_update(user_id)
    if subscription is None:
        raise ServiceError("подписка для компенсации не найдена", "subscription_missing")
    plan = await session.get(Plan, subscription.plan_id)
    if plan is None:  # pragma: no cover - subscription FK retains the plan
        raise ServiceError("тариф подписки не найден", "plan_not_found")
    before = _subscription_snapshot(subscription, plan.code)
    now = datetime.now(UTC)
    subscription.expires_at = max(now, subscription.expires_at - timedelta(days=days))
    subscription.status = (
        SubscriptionState.active if subscription.expires_at > now else SubscriptionState.expired
    )
    await subscriptions.add_event(
        user_id=user_id,
        type=SubscriptionEventType.admin_revoke,
        days_delta=-days,
        plan_id=subscription.plan_id,
        actor=SubscriptionActor.admin,
        actor_user_id=actor_id,
        origin_attempt_id=None,
        comment=comment,
        created_at=now,
    )
    await OutboxRepository(session).add(TOPIC_PROVISION, {"user_id": user_id})
    return before, _subscription_snapshot(subscription, plan.code)


def _subscription_snapshot(subscription: Subscription, plan_code: str) -> dict[str, object]:
    return {
        "user_id": subscription.user_id,
        "plan_code": plan_code,
        "status": subscription.status.value,
        "expires_at": subscription.expires_at.isoformat(),
    }


def _audit_snapshot(view: SubscriptionView | None) -> dict[str, str] | None:
    """Состояние подписки для журнала: тариф и срок, без служебных полей."""
    if view is None:
        return None
    return {"plan_code": view.plan_code, "expires_at": view.expires_at.isoformat()}


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


@router.get("/broadcasts", response_model=list[BroadcastResponse])
async def list_broadcasts(
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> list[BroadcastResponse]:
    """Свежие сверху: администратор ищет ту кампанию, что запустил только что."""
    return [_broadcast_response(item) for item in await BroadcastService(session).list_campaigns()]


@router.post("/broadcasts", response_model=BroadcastResponse, status_code=status.HTTP_201_CREATED)
async def create_broadcast(
    payload: CreateBroadcastRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
    ip: Annotated[str | None, Depends(client_ip)],
) -> BroadcastResponse:
    """Черновик кампании. Отправка начинается отдельным действием."""
    try:
        campaign = await BroadcastService(session).create(
            created_by=context.principal.user_id,
            segment=payload.segment,
            title=payload.title,
            body=payload.body,
        )
    except ServiceError as error:
        raise api_error_from_service(error) from error

    await _record_broadcast(session, "broadcast.create", campaign, context=context, ip=ip)
    await session.commit()
    return _broadcast_response(campaign)


@router.get("/broadcasts/{broadcast_id}", response_model=BroadcastResponse)
async def read_broadcast(
    broadcast_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> BroadcastResponse:
    return _broadcast_response(await _require_broadcast(session, broadcast_id))


@router.post("/broadcasts/{broadcast_id}/start", response_model=BroadcastResponse)
async def start_broadcast(
    broadcast_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
    ip: Annotated[str | None, Depends(client_ip)],
) -> BroadcastResponse:
    """Фиксирует аудиторию и переводит кампанию в работу."""
    try:
        # Сервис открывает транзакцию сам: аудиторию нельзя зафиксировать
        # наполовину. Открытая зависимостью транзакция уронила бы его begin().
        if session.in_transaction():
            await session.commit()
        await BroadcastService(session).start(broadcast_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error

    campaign = await _require_broadcast(session, broadcast_id)
    await _record_broadcast(session, "broadcast.start", campaign, context=context, ip=ip)
    await session.commit()
    return _broadcast_response(campaign)


@router.post("/broadcasts/{broadcast_id}/cancel", response_model=BroadcastResponse)
async def cancel_broadcast(
    broadcast_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
    ip: Annotated[str | None, Depends(client_ip)],
) -> BroadcastResponse:
    """Останавливает идущую кампанию. Уже отправленное не отзывается."""
    try:
        if session.in_transaction():
            await session.commit()
        await BroadcastService(session).cancel(broadcast_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error

    campaign = await _require_broadcast(session, broadcast_id)
    await _record_broadcast(session, "broadcast.cancel", campaign, context=context, ip=ip)
    await session.commit()
    return _broadcast_response(campaign)


@router.get("/segments/{segment}/count", response_model=SegmentCountResponse)
async def count_segment_reach(
    segment: str,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> SegmentCountResponse:
    """Охват до запуска — единственная защита от «отправил не тем»."""
    try:
        return SegmentCountResponse(count=await count_segment(session, segment))
    except KeyError as error:
        # segment_query отвергает неизвестное имя KeyError, а не ServiceError:
        # непойманный, он превратил бы опечатку в имени сегмента в 500.
        raise ApiError(f"неизвестный сегмент: {segment}", 422, "unknown_segment") from error


async def _require_broadcast(session: AsyncSession, broadcast_id: int) -> Broadcast:
    campaign = await session.get(Broadcast, broadcast_id)
    if campaign is None:
        raise ApiError("рассылка не найдена", 404, "not_found")
    return campaign


async def _record_broadcast(
    session: AsyncSession,
    action: str,
    campaign: Broadcast,
    *,
    context: AuthContext,
    ip: str | None,
) -> None:
    """След в журнале: письмо всей базе обязано иметь названного автора."""
    await AuditRepository(session).record(
        action,
        "broadcast",
        actor_id=context.principal.user_id,
        entity_id=str(campaign.id),
        after=_broadcast_snapshot(campaign),
        ip=ip,
    )


def _broadcast_snapshot(campaign: Broadcast) -> dict[str, object]:
    return {
        "segment": campaign.segment,
        "status": campaign.status.value,
        "planned_count": campaign.planned_count,
        "sent_count": campaign.sent_count,
        "failed_count": campaign.failed_count,
    }


def _broadcast_response(campaign: Broadcast) -> BroadcastResponse:
    return BroadcastResponse(
        id=campaign.id,
        segment=campaign.segment,
        title=campaign.title,
        body=campaign.body,
        status=campaign.status.value,
        planned_count=campaign.planned_count,
        sent_count=campaign.sent_count,
        failed_count=campaign.failed_count,
        started_at=campaign.started_at,
        finished_at=campaign.finished_at,
    )


@router.get("/tickets", response_model=list[AdminTicketResponse])
async def list_tickets(
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
    ticket_status: Annotated[TicketStatus | None, Query(alias="status")] = None,
) -> list[AdminTicketResponse]:
    """Очередь персонала: свежие сверху, отбор по тому, чьего хода ждём."""
    query = select(Ticket).order_by(Ticket.id.desc())
    if ticket_status is not None:
        query = query.where(Ticket.status == ticket_status)
    return [_admin_ticket_response(item) for item in (await session.scalars(query)).all()]


@router.get("/tickets/{ticket_id}", response_model=AdminTicketThreadResponse)
async def read_ticket_thread(
    ticket_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
) -> AdminTicketThreadResponse:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        raise ApiError("обращение не найдено", 404, "not_found")
    messages = await SupportService(session).thread(ticket_id)
    return AdminTicketThreadResponse(
        ticket=_admin_ticket_response(ticket),
        messages=[_ticket_message_response(message) for message in messages],
    )


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=TicketMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def reply_to_ticket(
    ticket_id: int,
    payload: TicketReplyRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
    ip: Annotated[str | None, Depends(client_ip)],
) -> TicketMessageResponse:
    """Ответ персонала из админки. Копия уходит и в топик супергруппы."""
    try:
        message = await SupportService(session).reply_from_admin(
            ticket_id, payload.body, author_user_id=context.principal.user_id
        )
    except ServiceError as error:
        raise api_error_from_service(error) from error

    await AuditRepository(session).record(
        "ticket.reply",
        "ticket",
        actor_id=context.principal.user_id,
        entity_id=str(ticket_id),
        after={"message_id": message.id},
        ip=ip,
    )
    await session.commit()
    return _ticket_message_response(message)


@router.post("/tickets/{ticket_id}/close", status_code=status.HTTP_204_NO_CONTENT)
async def close_ticket(
    ticket_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
    ip: Annotated[str | None, Depends(client_ip)],
) -> None:
    """Закрывает обращение и его топик. Повтор безобиден."""
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        raise ApiError("обращение не найдено", 404, "not_found")
    if ticket.status is TicketStatus.closed:
        # Повтор ничего не меняет и записи в журнале не заслуживает: она
        # означала бы ещё одно действие персонала, которого не было.
        return

    try:
        await SupportService(session).close(ticket_id, by_staff=True)
    except ServiceError as error:
        raise api_error_from_service(error) from error

    await AuditRepository(session).record(
        "ticket.close",
        "ticket",
        actor_id=context.principal.user_id,
        entity_id=str(ticket_id),
        after={"status": TicketStatus.closed.value},
        ip=ip,
    )
    await session.commit()


def _admin_ticket_response(ticket: Ticket) -> AdminTicketResponse:
    return AdminTicketResponse(
        id=ticket.id,
        status=ticket.status.value,
        subject=ticket.subject,
        created_at=ticket.created_at,
        last_staff_message_at=ticket.last_staff_message_at,
        user_id=ticket.user_id,
        telegram_topic_id=ticket.telegram_topic_id,
        last_user_message_at=ticket.last_user_message_at,
    )


def _ticket_message_response(message: TicketMessage) -> TicketMessageResponse:
    return TicketMessageResponse(
        id=message.id,
        author=message.author_kind.value,
        body=message.body,
        created_at=message.created_at,
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
