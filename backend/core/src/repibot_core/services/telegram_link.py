"""Привязка и отвязка Telegram.

Тихого слияния аккаунтов нет: при захвате Telegram оно отдало бы чужие
подписки. Человек берёт код в кабинете и предъявляет его боту — тогда обе
стороны доказаны.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.db.repositories.audit import AuditRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.domain.identity import LINK_CODE_TTL, can_unlink, generate_link_code
from repibot_core.services.auth.types import AuthError
from repibot_core.services.login_methods import login_methods
from repibot_core.settings import Settings

logger = logging.getLogger(__name__)

CODE_PREFIX = "telegram:link:"
# Пять попыток при алфавите из 31 символа и шести знаках: столкновение
# маловероятно, а бесконечный цикл при переполненном Valkey недопустим.
CODE_ATTEMPTS = 5


class BotUsername(Protocol):
    """Всё, что сервису нужно от Bot API. Протокол — чтобы тест не ходил в сеть."""

    async def username(self) -> str: ...


@dataclass(frozen=True, slots=True)
class LinkOffer:
    code: str
    url: str


class TelegramLinkService:
    def __init__(
        self, session: AsyncSession, settings: Settings, redis: Redis, bot_api: BotUsername
    ) -> None:
        self._session = session
        self._settings = settings
        self._redis = redis
        self._bot_api = bot_api
        self._users = UserRepository(session)
        self._audit = AuditRepository(session)

    async def issue_code(self, user_id: int) -> LinkOffer:
        user = await self._require_user(user_id)
        if user.telegram_id is not None:
            raise AuthError("telegram_already_linked", "Telegram уже привязан")

        code = await self._free_code()
        await self._redis.set(
            f"{CODE_PREFIX}{code}", str(user_id), ex=int(LINK_CODE_TTL.total_seconds())
        )
        bot = await self._bot_api.username()
        return LinkOffer(code=code, url=f"https://t.me/{bot}?start=link_{code}")

    async def redeem(
        self, code: str, *, telegram_id: int, username: str | None, first_name: str | None
    ) -> User:
        stored = await self._take_code(code)
        if stored is None:
            raise AuthError("token_invalid", "код недействителен или устарел")
        target = await self._require_user(int(stored))

        if target.telegram_id == telegram_id:
            return target
        if target.telegram_id is not None:
            raise AuthError("telegram_already_linked", "к аккаунту уже привязан другой Telegram")

        existing = await self._users.get_by_telegram_id(telegram_id)
        if existing is not None:
            await self._absorb(existing, target)

        target.telegram_id = telegram_id
        target.telegram_username = username
        if target.name is None:
            target.name = first_name
        await self._audit.record(
            "telegram.linked", "user", actor_id=target.id, entity_id=str(target.id)
        )
        await self._session.commit()
        return target

    async def unlink(self, user_id: int) -> None:
        user = await self._require_user(user_id)
        if user.telegram_id is None:
            raise AuthError("not_found", "Telegram не привязан")

        methods = await login_methods(self._session, user)
        if not can_unlink(methods, "telegram"):
            raise AuthError("last_login_method", "это единственный способ входа")

        await self._audit.record(
            "telegram.unlinked",
            "user",
            actor_id=user.id,
            entity_id=str(user.id),
            before={"telegram_id": user.telegram_id},
        )
        user.telegram_id = None
        user.telegram_username = None
        await self._session.commit()

    async def _absorb(self, duplicate: User, target: User) -> None:
        """Поглощает пустой дубль, созданный входом в MiniApp или письмом боту.

        Пустой — значит войти в него нельзя ничем, кроме самого Telegram. Такой
        аккаунт не хранит ничего, что можно потерять. Если же у него есть свой
        способ входа, за ним стоит отдельный человек или отдельная история
        покупок, и склеивать их автоматически нельзя.

        Проверка идёт до единой записи в базу: отказ обязан оставить обе стороны
        нетронутыми.
        """
        methods = await login_methods(self._session, duplicate)
        if methods.has_password or duplicate.email is not None or methods.passkey_count:
            raise AuthError("link_conflict", "у этого Telegram уже есть свой аккаунт")

        # Сессии дубля уходят вместе с ним по внешнему ключу: открытый MiniApp
        # перестанет отвечать, человек переоткроет его и войдёт уже в общий
        # аккаунт. Оставлять их живыми нельзя — они указывают на исчезнувшего
        # пользователя.
        await self._audit.record(
            "telegram.duplicate_absorbed",
            "user",
            actor_id=target.id,
            entity_id=str(duplicate.id),
            before={"user_id": duplicate.id, "telegram_id": duplicate.telegram_id},
            after={"user_id": target.id},
        )
        # Строка дубля исчезает отдельным flush до того, как целевой аккаунт
        # получит telegram_id: внутри одного flush SQLAlchemy отправляет UPDATE
        # раньше DELETE, и уникальный индекс по telegram_id сработал бы на
        # значении, которое вот-вот освободится.
        await self._session.delete(duplicate)
        await self._session.flush()
        logger.info("пустой дубль поглощён при привязке Telegram", extra={"user_id": target.id})

    async def _take_code(self, code: str) -> str | None:
        """Забирает код одним запросом: GETDEL не оставляет окна для второго предъявления.

        Клиент создаётся с `decode_responses=False`, поэтому возвращаются
        `bytes`; строка допускается на случай клиента с декодированием.
        """
        stored: object = await self._redis.getdel(f"{CODE_PREFIX}{code.strip().upper()}")
        if isinstance(stored, bytes):
            return stored.decode()
        if stored is None:
            return None
        return str(stored)

    async def _free_code(self) -> str:
        for _ in range(CODE_ATTEMPTS):
            code = generate_link_code()
            if not await self._redis.exists(f"{CODE_PREFIX}{code}"):
                return code
        msg = "не удалось подобрать свободный код привязки"
        raise RuntimeError(msg)

    async def _require_user(self, user_id: int) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthError("not_found", "пользователь не найден")
        return user
