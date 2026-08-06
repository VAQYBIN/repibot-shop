"""Привязка Telegram по коду: три состояния дубля и отвязка."""

from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.db.repositories.passkeys import PasskeyRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.services.auth.types import AuthError
from repibot_core.services.telegram_link import TelegramLinkService
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker


class FakeBotApi:
    """Имя бота — единственное, что нужно сервису от Bot API."""

    async def username(self) -> str:
        return "repibot_test_bot"


def _service(session: AsyncSession, redis: FakeRedis) -> TelegramLinkService:
    return TelegramLinkService(session, get_settings(), redis, FakeBotApi())


async def _web_user(session: AsyncSession, email: str = "user@example.org") -> User:
    users = UserRepository(session)
    user = await users.create(
        email=email,
        password_hash="argon2",
        referral_code=await users.next_referral_code(),
    )
    await session.commit()
    return user


async def _telegram_user(session: AsyncSession, telegram_id: int, **fields: object) -> User:
    users = UserRepository(session)
    user = await users.create(
        telegram_id=telegram_id, referral_code=await users.next_referral_code(), **fields
    )
    await session.commit()
    return user


async def test_code_links_unknown_telegram_account(db_session: AsyncSession) -> None:
    redis = FakeRedis()
    service = _service(db_session, redis)
    user = await _web_user(db_session)

    offer = await service.issue_code(user.id)
    linked = await service.redeem(offer.code, telegram_id=555, username="tester", first_name="Тест")

    assert linked.id == user.id
    assert linked.telegram_id == 555
    assert offer.url == f"https://t.me/repibot_test_bot?start=link_{offer.code}"


async def test_empty_duplicate_is_absorbed(db_session: AsyncSession) -> None:
    """Открыл MiniApp, потом зарегистрировался на сайте — должен остаться один аккаунт."""
    redis = FakeRedis()
    service = _service(db_session, redis)
    duplicate = await _telegram_user(db_session, 555, name="Тест")
    user = await _web_user(db_session)

    offer = await service.issue_code(user.id)
    linked = await service.redeem(offer.code, telegram_id=555, username=None, first_name="Тест")

    assert linked.id == user.id
    remaining = await db_session.execute(
        text("select count(*) from users where id = :id"), {"id": duplicate.id}
    )
    assert remaining.scalar_one() == 0


async def test_duplicate_with_its_own_password_is_refused(db_session: AsyncSession) -> None:
    """У дубля есть свой вход — склеивать нельзя: в подпроекте 3 там появятся деньги."""
    redis = FakeRedis()
    service = _service(db_session, redis)
    await _telegram_user(db_session, 555, email="tg@example.org", password_hash="argon2")
    user = await _web_user(db_session)

    offer = await service.issue_code(user.id)

    with pytest.raises(AuthError) as failure:
        await service.redeem(offer.code, telegram_id=555, username=None, first_name=None)
    assert failure.value.code == "link_conflict"


async def test_duplicate_with_only_an_email_is_refused(db_session: AsyncSession) -> None:
    """Почта без пароля — тоже свой вход: по ней восстанавливают доступ."""
    redis = FakeRedis()
    service = _service(db_session, redis)
    await _telegram_user(db_session, 555, email="tg@example.org")
    user = await _web_user(db_session)

    offer = await service.issue_code(user.id)

    with pytest.raises(AuthError) as failure:
        await service.redeem(offer.code, telegram_id=555, username=None, first_name=None)
    assert failure.value.code == "link_conflict"


async def test_duplicate_with_passkey_is_refused(db_session: AsyncSession) -> None:
    redis = FakeRedis()
    service = _service(db_session, redis)
    duplicate = await _telegram_user(db_session, 555)
    await PasskeyRepository(db_session).create(
        user_id=duplicate.id,
        credential_id=b"key",
        public_key=b"key",
        sign_count=0,
        transports=None,
        name="Ключ",
    )
    await db_session.commit()
    user = await _web_user(db_session)
    offer = await service.issue_code(user.id)

    with pytest.raises(AuthError) as failure:
        await service.redeem(offer.code, telegram_id=555, username=None, first_name=None)
    assert failure.value.code == "link_conflict"


async def test_refusal_leaves_the_database_untouched(db_session: AsyncSession) -> None:
    """Отказ не должен ничего сдвинуть: ни дубля тронуть, ни привязку записать."""
    redis = FakeRedis()
    service = _service(db_session, redis)
    duplicate = await _telegram_user(
        db_session, 555, email="tg@example.org", password_hash="argon2"
    )
    user = await _web_user(db_session)
    offer = await service.issue_code(user.id)
    # Идентификаторы запоминаются до отката: он гасит атрибуты объектов, и
    # обращение к ним после него ушло бы в базу вне greenlet-контекста.
    duplicate_id, user_id = duplicate.id, user.id

    with pytest.raises(AuthError):
        await service.redeem(offer.code, telegram_id=555, username="tester", first_name="Тест")

    # Сессию откатываем и читаем сырыми запросами: незакоммиченное изменение
    # иначе было бы видно в объектах и тест бы его не заметил.
    await db_session.rollback()
    rows = await db_session.execute(text("select id, telegram_id from users order by id"))
    assert set(rows.all()) == {(duplicate_id, 555), (user_id, None)}
    actions = await db_session.execute(text("select count(*) from audit_log"))
    assert actions.scalar_one() == 0


async def test_code_expires_after_first_use(db_session: AsyncSession) -> None:
    redis = FakeRedis()
    service = _service(db_session, redis)
    user = await _web_user(db_session)
    offer = await service.issue_code(user.id)
    await service.redeem(offer.code, telegram_id=555, username=None, first_name=None)

    with pytest.raises(AuthError) as failure:
        await service.redeem(offer.code, telegram_id=556, username=None, first_name=None)
    assert failure.value.code == "token_invalid"


async def test_account_with_telegram_gets_no_new_code(db_session: AsyncSession) -> None:
    redis = FakeRedis()
    service = _service(db_session, redis)
    user = await _telegram_user(db_session, 555, email="tg@example.org", password_hash="argon2")

    with pytest.raises(AuthError) as failure:
        await service.issue_code(user.id)
    assert failure.value.code == "telegram_already_linked"


async def test_unlink_needs_another_way_in(db_session: AsyncSession) -> None:
    redis = FakeRedis()
    service = _service(db_session, redis)
    user = await _telegram_user(db_session, 555)

    with pytest.raises(AuthError) as failure:
        await service.unlink(user.id)
    assert failure.value.code == "last_login_method"


async def test_unlink_works_when_password_remains(db_session: AsyncSession) -> None:
    redis = FakeRedis()
    service = _service(db_session, redis)
    user = await _telegram_user(db_session, 555, email="tg@example.org", password_hash="argon2")
    user.email_verified_at = user.created_at
    await db_session.commit()

    await service.unlink(user.id)

    assert user.telegram_id is None
    assert user.telegram_username is None


async def test_linking_is_written_to_the_audit_log(db_session: AsyncSession) -> None:
    redis = FakeRedis()
    service = _service(db_session, redis)
    user = await _web_user(db_session)
    offer = await service.issue_code(user.id)

    await service.redeem(offer.code, telegram_id=555, username=None, first_name=None)

    actions = await db_session.execute(text("select action from audit_log order by id"))
    assert "telegram.linked" in {row[0] for row in actions}
