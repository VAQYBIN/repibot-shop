"""Отказ от маркетинга по подписанной ссылке, без входа в аккаунт.

Требовать входа ради отписки значит удерживать человека там, откуда он хочет
уйти: он просто пометит письмо спамом, и это ударит по доставляемости всей
почты. Токен при этом не открывает ничего, кроме самой отписки.
"""

from __future__ import annotations

from datetime import UTC, datetime

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.services.errors import ServiceError
from repibot_core.settings import get_settings

ALGORITHM = "HS256"
PURPOSE = "unsubscribe"
# Кнопку ставит разбор очереди, а нажатие ловит бот — два разных процесса,
# которым нельзя разойтись в строке. Она живёт здесь, а не в боте: core о боте
# не знает, зато бот знает о core.
CALLBACK_DATA = "unsub"
_INVALID = "ссылка недействительна"


def sign_unsubscribe_token(user_id: int) -> str:
    """Срока жизни нет намеренно: ссылка из письма годовой давности обязана работать."""
    return jwt.encode(
        {"sub": str(user_id), "purpose": PURPOSE},
        get_settings().jwt_secret.get_secret_value(),
        algorithm=ALGORITHM,
    )


class UnsubscribeService:
    """Один вход для письма, кнопки бота и маршрута API."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def apply(self, token: str) -> None:
        """Помечает отказ от маркетинга. Транзакцию закрывает вызывающий.

        Все отказы отвечают одним кодом: разные коды для подделки, чужого
        назначения и удалённого аккаунта рассказали бы владельцу ссылки, что
        именно не так, и превратили бы маршрут в проверку чужих токенов.
        """
        try:
            claims = jwt.decode(
                token,
                get_settings().jwt_secret.get_secret_value(),
                algorithms=[ALGORITHM],
            )
        except jwt.PyJWTError as error:
            raise ServiceError(_INVALID, "invalid_token") from error
        # Назначение проверяется отдельно: access-токен подписан тем же
        # секретом, и без этой проверки он сошёл бы за ссылку отписки.
        if claims.get("purpose") != PURPOSE:
            raise ServiceError(_INVALID, "invalid_token")

        try:
            user_id = int(claims["sub"])
        except (KeyError, TypeError, ValueError) as error:
            raise ServiceError(_INVALID, "invalid_token") from error

        user = await self._session.get(User, user_id)
        if user is None:
            raise ServiceError(_INVALID, "invalid_token")
        # Момент первого отказа не переписывается повторным переходом по той же
        # ссылке: при разборе жалобы важно, когда человек отказался, а не когда
        # он последний раз нажал кнопку.
        if user.marketing_opt_out_at is None:
            user.marketing_opt_out_at = datetime.now(UTC)
