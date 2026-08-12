"""Блокировка аккаунта и заглушение поддержки."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import AuditLog, User, UserRole, UserStatus
from repibot_core.services.errors import ServiceError
from repibot_core.services.moderation import ModerationService

pytestmark = pytest.mark.docker

# Номер, которого в базе заведомо нет: схема пересоздаётся на каждый тест, и
# последовательность идентификаторов никогда не доходит до миллиона.
MISSING_USER_ID = 1_000_000


async def _user(session: AsyncSession, code: str, **fields: object) -> User:
    user = User(email=None, referral_code=code, **fields)
    session.add(user)
    await session.flush()
    await session.commit()
    return user


async def test_ban_records_who_did_it(db_session: AsyncSession) -> None:
    """Журнал нужен ровно для спора «за что меня заблокировали»."""
    staff = await _user(db_session, "mod00001", role=UserRole.support)
    target = await _user(db_session, "mod00002")

    changed = await ModerationService(db_session).ban(target.id, actor_id=staff.id)
    await db_session.commit()

    assert changed is True
    await db_session.refresh(target)
    assert target.status is UserStatus.banned
    record = await db_session.scalar(select(AuditLog).where(AuditLog.action == "user.ban"))
    assert record is not None
    assert record.actor_id == staff.id
    assert record.entity_id == str(target.id)


async def test_second_ban_changes_nothing(db_session: AsyncSession) -> None:
    """Повтор не должен плодить записи журнала и подтверждать несделанное."""
    target = await _user(db_session, "mod00003", status=UserStatus.banned)

    assert await ModerationService(db_session).ban(target.id, actor_id=None) is False
    await db_session.commit()

    assert await db_session.scalar(select(AuditLog)) is None


async def test_staff_cannot_be_banned(db_session: AsyncSession) -> None:
    """Одной командой из рабочего чата гасился бы доступ коллеги."""
    colleague = await _user(db_session, "mod00004", role=UserRole.admin)

    with pytest.raises(ServiceError) as refusal:
        await ModerationService(db_session).ban(colleague.id, actor_id=None)

    assert refusal.value.code == "staff_immune"


async def test_unban_returns_the_account_to_work(db_session: AsyncSession) -> None:
    """Разбан обязан оставить след не меньше, чем сам бан: снятие тоже решение."""
    staff = await _user(db_session, "mod00005", role=UserRole.support)
    target = await _user(db_session, "mod00006", status=UserStatus.banned)

    changed = await ModerationService(db_session).unban(target.id, actor_id=staff.id)
    await db_session.commit()

    assert changed is True
    await db_session.refresh(target)
    assert target.status is UserStatus.active
    record = await db_session.scalar(select(AuditLog).where(AuditLog.action == "user.unban"))
    assert record is not None
    assert record.actor_id == staff.id


async def test_unban_of_a_free_account_changes_nothing(db_session: AsyncSession) -> None:
    """Сотруднику важно услышать «он и не был заблокирован», а не «снял»."""
    target = await _user(db_session, "mod00007")

    assert await ModerationService(db_session).unban(target.id, actor_id=None) is False
    await db_session.commit()

    assert await db_session.scalar(select(AuditLog)) is None


async def test_mute_marks_the_moment_support_was_closed(db_session: AsyncSession) -> None:
    """Хранится момент, а не флаг: при разборе жалобы важно, когда закрыли."""
    staff = await _user(db_session, "mod00008", role=UserRole.support)
    target = await _user(db_session, "mod00009")

    changed = await ModerationService(db_session).mute_support(target.id, actor_id=staff.id)
    await db_session.commit()

    assert changed is True
    await db_session.refresh(target)
    assert target.support_muted_at is not None
    # Бан заглушением не ставится: закрыт разговор, а не подписка и оплата.
    assert target.status is UserStatus.active
    record = await db_session.scalar(select(AuditLog).where(AuditLog.action == "user.support_mute"))
    assert record is not None
    assert record.entity_id == str(target.id)


async def test_second_mute_changes_nothing(db_session: AsyncSession) -> None:
    """Повторное заглушение сдвинуло бы момент и стёрло бы, когда закрыли на самом деле."""
    target = await _user(db_session, "mod00010")
    service = ModerationService(db_session)
    await service.mute_support(target.id, actor_id=None)
    await db_session.commit()
    muted_at = target.support_muted_at

    assert await service.mute_support(target.id, actor_id=None) is False
    await db_session.commit()

    await db_session.refresh(target)
    assert target.support_muted_at == muted_at
    assert len(list(await db_session.scalars(select(AuditLog)))) == 1


async def test_unmute_opens_the_conversation_again(db_session: AsyncSession) -> None:
    """Снятие обнуляет момент: пустота и есть признак открытой поддержки."""
    target = await _user(db_session, "mod00011")
    service = ModerationService(db_session)
    await service.mute_support(target.id, actor_id=None)
    await db_session.commit()

    changed = await service.unmute_support(target.id, actor_id=None)
    await db_session.commit()

    assert changed is True
    await db_session.refresh(target)
    assert target.support_muted_at is None
    record = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "user.support_unmute")
    )
    assert record is not None


async def test_unmute_of_an_open_account_changes_nothing(db_session: AsyncSession) -> None:
    """«Поддержка и так открыта» — единственный честный ответ на такую команду."""
    target = await _user(db_session, "mod00012")

    assert await ModerationService(db_session).unmute_support(target.id, actor_id=None) is False
    await db_session.commit()

    assert await db_session.scalar(select(AuditLog)) is None


async def test_unknown_person_is_not_found(db_session: AsyncSession) -> None:
    """Тема живёт дольше аккаунта: команда по удалённому не должна ронять бота."""
    service = ModerationService(db_session)

    for action in (service.ban, service.unban, service.mute_support, service.unmute_support):
        with pytest.raises(ServiceError) as refusal:
            await action(MISSING_USER_ID, actor_id=None)
        assert refusal.value.code == "not_found"
