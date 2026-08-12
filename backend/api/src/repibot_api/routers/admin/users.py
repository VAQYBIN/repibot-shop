"""Пользователи в админке: поиск, карточка, журнал, действия над человеком.

Главный экран рабочего места: половина обращений решается тем, что сотрудник
видит человека целиком и может тут же что-то поправить. Поэтому предмет открыт
обеим ролям, а деньги — начисление дней и смена тарифа — остаются в модуле
orders и только у администратора.

Схемы ответов объявлены здесь, а не в общем `schemas.py`: соседние предметы
админки наполняются одновременно, и общий файл стал бы местом столкновения.
Прецедент — `WhoAmIResponse` в корне пакета.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import AuthContext, client_ip, db_session, require_role
from repibot_api.errors import ApiError, api_error_from_service
from repibot_api.schemas import DeviceResponse, DevicesResponse
from repibot_api.subscription_view import device_service, panel_client
from repibot_core.db.models import User, UserRole
from repibot_core.db.repositories.audit import AuditRepository
from repibot_core.integrations.remnawave.client import RemnawaveError
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.admin_users import JournalEntry, UserCard, UserRow, search_users
from repibot_core.services.admin_users import user_card as build_card
from repibot_core.services.admin_users import user_journal as build_journal
from repibot_core.services.devices import DeviceService
from repibot_core.services.errors import ServiceError
from repibot_core.services.moderation import ModerationService

# Без префикса: он стоит на общем роутере пакета.
router = APIRouter()


class AdminUserRowResponse(BaseModel):
    id: int
    name: str | None
    email: str | None
    telegram_id: int | None
    telegram_username: str | None
    plan_name: str | None
    subscription_status: str | None
    expires_at: datetime | None
    banned: bool
    support_muted: bool


class AdminUserCardResponse(BaseModel):
    # Строка списка вложена целиком, а не переписана полями: карточка и список
    # показывают одно и то же о человеке, и разошлись бы на первой же правке.
    row: AdminUserRowResponse
    language: str
    role: str
    created_at: datetime
    email_verified: bool
    referred_by_id: int | None
    subscription_source: str | None
    auto_renew: bool
    subscription_url: str | None
    remnawave_id: int | None


class AdminJournalEntryResponse(BaseModel):
    at: datetime
    kind: str
    title: str
    detail: str | None
    actor: str | None


class AdminModerationResponse(BaseModel):
    # Интерфейсу нужно отличать «заблокировали» от «уже был заблокирован»:
    # второе означает, что коллега успел раньше.
    changed: bool


class AdminSubscriptionLinkResponse(BaseModel):
    subscription_url: str
    short_uuid: str


@router.get("/users", response_model=list[AdminUserRowResponse])
async def list_users(
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
    query: Annotated[str, Query(max_length=320)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminUserRowResponse]:
    """Поиск по любому опознавателю: почта, @имя, номер Telegram, аккаунта или панели.

    Разбирает строку сервер: сотрудник не знает, что ему прислали, и выбирать
    поле поиска руками не должен. Пустая строка отдаёт свежих сверху.
    """
    found = await search_users(session, query, limit=limit, offset=offset)
    return [_row_response(row) for row in found]


@router.get("/users/{user_id}", response_model=AdminUserCardResponse)
async def read_user_card(
    user_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
) -> AdminUserCardResponse:
    """Карточка без устройств: их отдаёт панель, и отдельным маршрутом."""
    card = await build_card(session, user_id)
    if card is None:
        raise ApiError("пользователь не найден", 404, "not_found")
    return _card_response(card)


@router.get("/users/{user_id}/journal", response_model=list[AdminJournalEntryResponse])
async def read_user_journal(
    user_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AdminJournalEntryResponse]:
    """Начисления, деньги и решения персонала одной лентой, свежее сверху.

    Склейка на сервере: три ленты, собранные в браузере, дали бы три запроса и
    разъезжающуюся разбивку по страницам.
    """
    await _require_user(session, user_id)
    entries = await build_journal(session, user_id, limit=limit)
    return [_journal_response(entry) for entry in entries]


@router.get("/users/{user_id}/devices", response_model=DevicesResponse)
async def read_user_devices(
    user_id: int,
    devices: Annotated[DeviceService, Depends(device_service)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
) -> DevicesResponse:
    """Устройства из панели. Её молчание гасит только этот блок, а не карточку."""
    try:
        view = await devices.list(user_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except RemnawaveError as error:
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error
    return DevicesResponse(
        devices=[
            DeviceResponse(
                hwid=item.hwid,
                platform=item.platform,
                device_model=item.device_model,
                os_version=item.os_version,
                created_at=item.created_at,
            )
            for item in view.devices
        ],
        limit=view.limit,
        used=view.used,
    )


@router.delete("/users/{user_id}/devices/{hwid}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_user_device(
    user_id: int,
    hwid: str,
    session: Annotated[AsyncSession, Depends(db_session)],
    devices: Annotated[DeviceService, Depends(device_service)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
    ip: Annotated[str | None, Depends(client_ip)],
) -> None:
    """Отвязка устройства за человека: он сменил телефон и не разобрался сам.

    hwid стоит в адресе, а не в теле, как в кабинете: сотрудник не набирает его
    руками, а нажимает на строку только что показанного списка.
    """
    try:
        await devices.unlink(user_id, hwid)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except RemnawaveError as error:
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error

    # Своей записи в журнале у сервиса устройств нет: он ходит и за самим
    # человеком, для которого это не решение персонала.
    await AuditRepository(session).record(
        "user.device_unlink",
        "user",
        actor_id=context.principal.user_id,
        entity_id=str(user_id),
        after={"hwid": hwid},
        ip=ip,
    )
    await session.commit()


@router.post("/users/{user_id}/block", response_model=AdminModerationResponse)
async def block_user(
    user_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
) -> AdminModerationResponse:
    """Закрывает аккаунт целиком: и покупки, и разговор."""
    return await _moderate(ModerationService(session).ban, user_id, session, context)


@router.post("/users/{user_id}/unblock", response_model=AdminModerationResponse)
async def unblock_user(
    user_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
) -> AdminModerationResponse:
    """Возвращает аккаунт в работу."""
    return await _moderate(ModerationService(session).unban, user_id, session, context)


@router.post("/users/{user_id}/mute", response_model=AdminModerationResponse)
async def mute_user(
    user_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
) -> AdminModerationResponse:
    """Закрывает разговор, оставляя подписку, кабинет и оплату нетронутыми."""
    return await _moderate(ModerationService(session).mute_support, user_id, session, context)


@router.post("/users/{user_id}/unmute", response_model=AdminModerationResponse)
async def unmute_user(
    user_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
) -> AdminModerationResponse:
    """Снова открывает разговор."""
    return await _moderate(ModerationService(session).unmute_support, user_id, session, context)


@router.post(
    "/users/{user_id}/subscription/revoke-link", response_model=AdminSubscriptionLinkResponse
)
async def revoke_subscription_link(
    user_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.support, UserRole.admin))],
    ip: Annotated[str | None, Depends(client_ip)],
) -> AdminSubscriptionLinkResponse:
    """Выпускает новую ссылку подписки взамен утёкшей.

    Панель меняет shortUuid, и наш адрес перезаписывается её ответом: иначе
    кабинет продолжит показывать мёртвую ссылку. До ответа панели в базу не
    пишется ничего, поэтому её молчание нечего откатывать.
    """
    user = await _require_user(session, user_id)
    if user.remnawave_id is None:
        raise ApiError("в панели этого человека ещё нет", 404, "subscription_missing")

    client = panel_client()
    try:
        panel_user = await PanelUsers(client).revoke(user.remnawave_id)
    except RemnawaveError as error:
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error
    finally:
        # Клиент закрывается и на отказе: httpx держит пул соединений, и без
        # закрытия сокеты живут до сборки мусора.
        await client.aclose()

    before = user.remnawave_subscription_url
    user.remnawave_short_uuid = panel_user.shortUuid
    user.remnawave_subscription_url = panel_user.subscriptionUrl
    # Новая ссылка гасит доступ на всех устройствах человека — такое решение
    # обязано оставить след, и своего журнала у фасада панели нет.
    await AuditRepository(session).record(
        "user.subscription_link_revoke",
        "user",
        actor_id=context.principal.user_id,
        entity_id=str(user_id),
        before={"subscription_url": before},
        after={"subscription_url": panel_user.subscriptionUrl},
        ip=ip,
    )
    await session.commit()
    return AdminSubscriptionLinkResponse(
        subscription_url=panel_user.subscriptionUrl, short_uuid=panel_user.shortUuid
    )


async def _require_user(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise ApiError("пользователь не найден", 404, "not_found")
    return user


async def _moderate(
    action: Callable[..., Awaitable[bool]],
    user_id: int,
    session: AsyncSession,
    context: AuthContext,
) -> AdminModerationResponse:
    """Общая обвязка четырёх решений персонала.

    Запись в журнал делает сам `ModerationService` — та же, что и у команды в
    теме поддержки. Второй записи здесь не нужно: одно решение — одна строка.
    """
    try:
        changed = await action(user_id, actor_id=context.principal.user_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    await session.commit()
    return AdminModerationResponse(changed=changed)


def _row_response(row: UserRow) -> AdminUserRowResponse:
    return AdminUserRowResponse(
        id=row.id,
        name=row.name,
        email=row.email,
        telegram_id=row.telegram_id,
        telegram_username=row.telegram_username,
        plan_name=row.plan_name,
        subscription_status=row.subscription_status,
        expires_at=row.expires_at,
        banned=row.banned,
        support_muted=row.support_muted,
    )


def _card_response(card: UserCard) -> AdminUserCardResponse:
    return AdminUserCardResponse(
        row=_row_response(card.row),
        language=card.language,
        role=card.role,
        created_at=card.created_at,
        email_verified=card.email_verified,
        referred_by_id=card.referred_by_id,
        subscription_source=card.subscription_source,
        auto_renew=card.auto_renew,
        subscription_url=card.subscription_url,
        remnawave_id=card.remnawave_id,
    )


def _journal_response(entry: JournalEntry) -> AdminJournalEntryResponse:
    return AdminJournalEntryResponse(
        at=entry.at, kind=entry.kind, title=entry.title, detail=entry.detail, actor=entry.actor
    )
