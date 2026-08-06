"""Passkey: регистрация ключа, вход без пароля, удаление."""

from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn.helpers import base64url_to_bytes

from repibot_core.db.models import User, UserStatus
from repibot_core.db.repositories.users import UserRepository
from repibot_core.security.webauthn import relying_party
from repibot_core.services.auth.passkey import PasskeyAuth
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError
from repibot_core.services.challenges import ChallengeStore
from repibot_core.services.principal import PrincipalCache
from repibot_core.settings import get_settings
from repibot_core.testing.webauthn import SoftAuthenticator

pytestmark = pytest.mark.docker


def _device(credential_id: bytes | None = None) -> SoftAuthenticator:
    party = relying_party(get_settings().public_web_url)
    return SoftAuthenticator(rp_id=party.rp_id, origin=party.origin, credential_id=credential_id)


def _service(session: AsyncSession) -> PasskeyAuth:
    settings = get_settings()
    redis = FakeRedis()
    auth = AuthService(session, settings, PrincipalCache(redis))
    return PasskeyAuth(session, settings, auth, ChallengeStore(redis))


async def _user(session: AsyncSession, **fields: object) -> User:
    users = UserRepository(session)
    user = await users.create(
        email="user@example.org", referral_code=await users.next_referral_code(), **fields
    )
    await session.commit()
    return user


async def _register(service: PasskeyAuth, user: User, device: SoftAuthenticator) -> None:
    options = await service.registration_options(user.id)
    challenge = base64url_to_bytes(str(options["challenge"]))
    await service.register(user.id, device.register(challenge), name="Ноутбук")


async def _login_challenge(service: PasskeyAuth) -> bytes:
    options = await service.login_options()
    return base64url_to_bytes(str(options["challenge"]))


async def test_registered_key_lets_the_user_in(db_session: AsyncSession) -> None:
    user = await _user(db_session, password_hash="argon2")
    service = _service(db_session)
    device = _device()
    await _register(service, user, device)

    challenge = await _login_challenge(service)
    issued = await service.login(
        device.authenticate(challenge, user_handle=str(user.id).encode()),
        user_agent="pytest",
        ip="127.0.0.1",
    )

    assert issued.refresh_token is not None
    assert issued.session_id is not None


async def test_challenge_works_only_once(db_session: AsyncSession) -> None:
    """Записанный ответ не должен пускать в аккаунт второй раз."""
    user = await _user(db_session, password_hash="argon2")
    service = _service(db_session)
    device = _device()
    await _register(service, user, device)

    challenge = await _login_challenge(service)
    reply = device.authenticate(challenge, user_handle=str(user.id).encode())
    await service.login(reply, user_agent=None, ip=None)

    with pytest.raises(AuthError) as failure:
        await service.login(reply, user_agent=None, ip=None)
    assert failure.value.code == "token_invalid"


async def test_foreign_challenge_is_refused(db_session: AsyncSession) -> None:
    """Challenge, которого сервер не выдавал, не принимается."""
    user = await _user(db_session, password_hash="argon2")
    service = _service(db_session)
    device = _device()
    await _register(service, user, device)

    with pytest.raises(AuthError) as failure:
        await service.login(
            device.authenticate("самодельный challenge".encode(), user_handle=b"1"),
            user_agent=None,
            ip=None,
        )
    assert failure.value.code == "token_invalid"


async def test_forged_signature_hides_the_reason(db_session: AsyncSession) -> None:
    """Подделка отклоняется общим кодом: подробность помогает подбирающему."""
    user = await _user(db_session, password_hash="argon2")
    service = _service(db_session)
    device = _device()
    await _register(service, user, device)

    # Тот же идентификатор ключа, другая пара ключей: запись в базе найдётся,
    # а подпись под ней не сойдётся.
    impostor = _device(credential_id=device.credential_id)
    challenge = await _login_challenge(service)

    with pytest.raises(AuthError) as failure:
        await service.login(
            impostor.authenticate(challenge, user_handle=str(user.id).encode()),
            user_agent=None,
            ip=None,
        )
    assert failure.value.code == "invalid_credentials"


async def test_last_login_method_cannot_be_deleted(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    service = _service(db_session)
    device = _device()
    await _register(service, user, device)
    keys = await service.list_keys(user.id)

    with pytest.raises(AuthError) as failure:
        await service.delete(user.id, keys[0].id)
    assert failure.value.code == "last_login_method"


async def test_key_of_another_user_is_not_found(db_session: AsyncSession) -> None:
    """Чужой ключ не удаляется и о его существовании не сообщается."""
    owner = await _user(db_session, password_hash="argon2")
    service = _service(db_session)
    await _register(service, owner, _device())
    keys = await service.list_keys(owner.id)

    users = UserRepository(db_session)
    stranger = await users.create(
        email="other@example.org", referral_code=await users.next_referral_code()
    )
    await db_session.commit()

    with pytest.raises(AuthError) as failure:
        await service.delete(stranger.id, keys[0].id)
    assert failure.value.code == "not_found"


async def test_banned_user_cannot_sign_in_with_passkey(db_session: AsyncSession) -> None:
    """Статус проверяется в AuthService: способ входа его не обходит."""
    user = await _user(db_session, password_hash="argon2")
    service = _service(db_session)
    device = _device()
    await _register(service, user, device)
    user.status = UserStatus.banned
    await db_session.commit()

    challenge = await _login_challenge(service)
    with pytest.raises(AuthError) as failure:
        await service.login(
            device.authenticate(challenge, user_handle=str(user.id).encode()),
            user_agent=None,
            ip=None,
        )
    assert failure.value.code == "forbidden"
