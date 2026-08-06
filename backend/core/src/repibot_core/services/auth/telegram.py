"""Вход через Telegram: MiniApp и браузер через OIDC.

Оба способа устроены одинаково: опознать человека и отдать пользователя
AuthService. Различаются они только тем, кто ручается за личность — подпись
initData или ID-токен oauth.telegram.org — и выдаётся ли refresh.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.db.repositories.users import UserRepository
from repibot_core.integrations.telegram.oidc import OidcIdentity
from repibot_core.security.initdata import InitDataError, TelegramUser, parse_init_data
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError, IssuedSession
from repibot_core.settings import Settings

logger = logging.getLogger(__name__)

# Сутки — предел свежести initData. Telegram выдаёт его при каждом открытии,
# и суточной давности значение означает переигранный запрос.
INIT_DATA_MAX_AGE = timedelta(days=1)


class TelegramAuth:
    def __init__(self, session: AsyncSession, settings: Settings, auth: AuthService) -> None:
        self._session = session
        self._settings = settings
        self._auth = auth
        self._users = UserRepository(session)

    async def login_from_miniapp(self, raw_init_data: str, *, ip: str | None) -> IssuedSession:
        try:
            parsed = parse_init_data(
                raw_init_data,
                bot_token=self._settings.bot_token.get_secret_value(),
                max_age=INIT_DATA_MAX_AGE,
            )
        except InitDataError as error:
            # Наружу уходит общий код: подробность «подпись не совпала» или
            # «устарел» помогает только тому, кто подбирает подпись.
            logger.warning("отклонён initData: %s", error)
            raise AuthError("invalid_credentials", "initData не принят") from error

        user = await self._find_or_create(parsed)
        # Refresh не выдаётся: в веб-версии Telegram наш домен оказывается в
        # стороннем контексте, и cookie там не переживёт перезагрузку.
        return await self._auth.issue(
            user, user_agent="telegram-miniapp", ip=ip, with_refresh=False
        )

    async def login_from_oidc(
        self, identity: OidcIdentity, *, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        """Вход через oauth.telegram.org.

        Подпись ID-токена проверена вызывающим: сюда приходит уже опознанный
        человек. Дальше путь общий с MiniApp — тот же поиск аккаунта и тот же
        AuthService, иначе один человек завёл бы два аккаунта в зависимости от
        того, откуда вошёл.
        """
        # OIDC даёт меньше, чем initData: языка в ID-токене нет вовсе, и
        # None здесь означает «выбрать язык по умолчанию», а не «сбросить».
        user = await self._find_or_create(
            TelegramUser(
                telegram_id=identity.telegram_id,
                username=identity.username,
                first_name=identity.name,
                language_code=None,
            )
        )
        # Refresh выдаётся, в отличие от MiniApp: обычный браузер держит нашу
        # cookie в первом контексте, и сессия переживает перезагрузку.
        return await self._auth.issue(user, user_agent=user_agent, ip=ip, with_refresh=True)

    async def _find_or_create(self, parsed: TelegramUser) -> User:
        user = await self._users.get_by_telegram_id(parsed.telegram_id)
        if user is not None:
            user.telegram_username = parsed.username
            if user.name is None:
                user.name = parsed.first_name
            await self._session.flush()
            return user

        language = self._pick_language(parsed.language_code)
        return await self._users.create(
            telegram_id=parsed.telegram_id,
            telegram_username=parsed.username,
            name=parsed.first_name,
            language=language,
            referral_code=await self._users.next_referral_code(),
        )

    def _pick_language(self, code: str | None) -> str:
        """Язык из Telegram — только начальное значение.

        Дальше он меняется исключительно пользователем: перенастройка Telegram
        не должна переключать язык кабинета.
        """
        if code is None:
            return self._settings.default_language
        short = code.split("-")[0]
        if short in self._settings.supported_languages:
            return short
        return self._settings.default_language
