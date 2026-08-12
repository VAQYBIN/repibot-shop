"""Переписка с поддержкой: модели, сервис, лимиты."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    NotificationDelivery,
    OutboxMessage,
    Ticket,
    TicketAuthor,
    TicketMessage,
    TicketStatus,
    User,
)
from repibot_core.services.errors import ServiceError
from repibot_core.services.support import (
    ADMIN_REPLY_MARK,
    TOPIC_SUPPORT_OUTBOUND,
    SupportService,
)
from repibot_core.settings import Settings

pytestmark = pytest.mark.docker

# Идентификатор супергруппы с топиками. Настройки собираются явно и передаются
# в сервис: monkeypatch окружения пришлось бы сопровождать сбросом глобального
# кэша, а забытый сброс портит соседние наборы, а не этот.
SUPPORT_CHAT_ID = -1_001_234_567_890


def _settings(**overrides: object) -> Settings:
    return Settings(support_chat_id=SUPPORT_CHAT_ID, **overrides)  # type: ignore[arg-type]


def _service(session: AsyncSession, **overrides: object) -> SupportService:
    return SupportService(session, _settings(**overrides))


async def _user(session: AsyncSession, telegram_id: int, code: str) -> User:
    user = User(email=None, telegram_id=telegram_id, referral_code=code)
    session.add(user)
    await session.flush()
    await session.commit()
    return user


async def test_ticket_starts_waiting_for_staff(db_session: AsyncSession) -> None:
    """Статус называет, чьего хода ждём: это всё, что нужно и очереди, и человеку."""
    user = User(email=None, telegram_id=300_001, referral_code="ticket01")
    db_session.add(user)
    await db_session.flush()
    ticket = Ticket(user_id=user.id, status=TicketStatus.waiting_staff, subject="Не открывается")
    db_session.add(ticket)
    await db_session.flush()
    db_session.add(
        TicketMessage(ticket_id=ticket.id, author_kind=TicketAuthor.user, body="Не открывается")
    )
    await db_session.commit()

    stored = await db_session.scalar(select(TicketMessage))
    assert stored is not None
    assert stored.author_kind is TicketAuthor.user
    assert ticket.telegram_topic_id is None


async def test_open_tickets_are_capped(db_session: AsyncSession) -> None:
    """Три открытых обращения — предел: у человека одновременно может сломаться
    оплата и доступ, но не десять вещей сразу."""
    user = await _user(db_session, 300_002, "ticket02")
    service = _service(db_session)
    for index in range(3):
        await service.open(user.id, f"вопрос {index}")
    await db_session.commit()

    with pytest.raises(ServiceError) as refusal:
        await service.open(user.id, "четвёртый")

    assert refusal.value.code == "too_many_tickets"


async def test_closed_tickets_stop_counting_against_the_limit(db_session: AsyncSession) -> None:
    """Иначе человек с тремя решёнными обращениями больше никогда не напишет."""
    user = await _user(db_session, 300_010, "ticket10")
    service = _service(db_session)
    first = await service.open(user.id, "первый")
    for index in range(2):
        await service.open(user.id, f"вопрос {index}")
    await service.close(first.id, by_staff=True, notify=False)
    await db_session.commit()

    reopened = await service.open(user.id, "четвёртый после закрытия")
    await db_session.commit()

    assert reopened.status is TicketStatus.waiting_staff


async def test_opening_only_queues_the_supergroup_task(db_session: AsyncSession) -> None:
    """Сервис не ходит в Telegram сам.

    Недоступная супергруппа не должна терять обращение, за которое человек уже
    заплатил ожиданием: топик создаст разбор очереди, а обращение уже в базе.
    """
    user = await _user(db_session, 300_004, "ticket04")

    ticket = await _service(db_session).open(user.id, "  не открывается  ")
    await db_session.commit()

    queued = (await db_session.scalars(select(OutboxMessage))).all()
    assert [message.topic for message in queued] == [TOPIC_SUPPORT_OUTBOUND]
    assert queued[0].payload["ticket_id"] == ticket.id
    assert queued[0].payload["body"] == "не открывается"
    assert ticket.telegram_topic_id is None


async def test_long_first_message_becomes_a_readable_topic_name(db_session: AsyncSession) -> None:
    """Тема топика — первые слова обращения: в списке тем персонал различает
    обращения, не открывая каждое. Bot API длинное имя темы просто отвергнет."""
    user = await _user(db_session, 300_011, "ticket11")

    ticket = await _service(db_session).open(user.id, "ж" * 400)
    await db_session.commit()

    assert len(ticket.subject) == 120


async def test_empty_message_does_not_open_a_ticket(db_session: AsyncSession) -> None:
    """Пустое обращение — это топик без вопроса, на который персоналу нечего ответить."""
    user = await _user(db_session, 300_005, "ticket05")

    with pytest.raises(ServiceError) as refusal:
        await _service(db_session).open(user.id, "   \n  ")

    assert refusal.value.code == "validation_error"


async def test_support_without_a_supergroup_is_refused(db_session: AsyncSession) -> None:
    """Стенд без супергруппы обязан подниматься и честно отвечать отказом."""
    user = await _user(db_session, 300_006, "ticket06")
    service = SupportService(db_session, Settings(support_chat_id=None))

    with pytest.raises(ServiceError) as refusal:
        await service.open(user.id, "привет")

    assert refusal.value.code == "support_unavailable"
    assert service.enabled() is False


async def test_muted_person_cannot_open_a_ticket(db_session: AsyncSession) -> None:
    """Заглушение закрывает разговор, а не подписку: отказ приходит здесь."""
    user = await _user(db_session, 300_100, "ticket90")
    user.support_muted_at = datetime.now(UTC)
    await db_session.commit()

    with pytest.raises(ServiceError) as refusal:
        await _service(db_session).open(user.id, "впустите")

    assert refusal.value.code == "support_muted"


async def test_muted_person_cannot_reply_in_an_open_ticket(db_session: AsyncSession) -> None:
    """Заглушение накладывают посреди разговора, и старое обращение осталось бы
    лазейкой: сотрудник закрывает его сам, а человек в него уже не пишет."""
    user = await _user(db_session, 300_104, "ticket94")
    service = _service(db_session)
    ticket = await service.open(user.id, "вопрос")
    user.support_muted_at = datetime.now(UTC)
    await db_session.commit()

    with pytest.raises(ServiceError) as refusal:
        await service.reply_from_user(user.id, ticket.id, "и ещё вот что")

    assert refusal.value.code == "support_muted"


async def test_muted_person_keeps_reading_the_thread(db_session: AsyncSession) -> None:
    """Закрыт разговор, а не переписка: без этого человек теряет доказательство
    того, что ему обещала поддержка."""
    user = await _user(db_session, 300_105, "ticket95")
    service = _service(db_session)
    ticket = await service.open(user.id, "вопрос")
    user.support_muted_at = datetime.now(UTC)
    await db_session.commit()

    assert [item.id for item in await service.list_for_user(user.id)] == [ticket.id]
    assert [item.body for item in await service.thread(ticket.id)] == ["вопрос"]


async def test_staff_reply_switches_the_turn_and_notifies(db_session: AsyncSession) -> None:
    """Ответ сотрудника обязан дойти до человека, а не остаться в топике."""
    user = await _user(db_session, 300_003, "ticket03")
    service = _service(db_session)
    ticket = await service.open(user.id, "не открывается")
    ticket.telegram_topic_id = 555
    await db_session.commit()

    message = await service.reply_from_staff(
        555, "Проверьте профиль", telegram_id=777, message_id=42
    )
    await db_session.commit()

    assert message is not None
    assert message.author_telegram_id == 777
    assert message.telegram_message_id == 42
    assert ticket.status is TicketStatus.waiting_user
    assert ticket.last_staff_message_at is not None
    kinds = list((await db_session.scalars(select(NotificationDelivery.kind))).all())
    assert kinds == ["ticket_reply"]


async def test_staff_reply_notification_carries_the_text(db_session: AsyncSession) -> None:
    """Ключ i18n подставляет `{body}`: без него человек получит письмо без ответа."""
    user = await _user(db_session, 300_012, "ticket12")
    service = _service(db_session)
    ticket = await service.open(user.id, "не открывается")
    ticket.telegram_topic_id = 556
    await db_session.commit()

    await service.reply_from_staff(556, "Проверьте профиль", telegram_id=777, message_id=43)
    await db_session.commit()

    notify = await db_session.scalar(
        select(OutboxMessage).where(OutboxMessage.topic.like("notify.%"))
    )
    assert notify is not None
    assert notify.payload["body"] == "Проверьте профиль"


async def test_staff_reply_asks_to_repaint_the_topic(db_session: AsyncSession) -> None:
    """Ответ из темы меняет состояние, но в Telegram ничего не отправляет:
    без этой просьбы название осталось бы красным на решённом обращении."""
    user = await _user(db_session, 300_103, "ticket93")
    service = _service(db_session)
    ticket = await service.open(user.id, "вопрос")
    ticket.telegram_topic_id = 4242
    await db_session.commit()

    await service.reply_from_staff(4242, "ответ", telegram_id=999, message_id=1)
    await db_session.commit()

    payloads = list(
        (
            await db_session.scalars(
                select(OutboxMessage.payload).where(OutboxMessage.topic == TOPIC_SUPPORT_OUTBOUND)
            )
        ).all()
    )
    assert {"ticket_id": ticket.id, "sync": True} in payloads


async def test_admin_reply_does_not_ask_to_repaint_twice(db_session: AsyncSession) -> None:
    """Ответ из админки и так кладёт в очередь копию с текстом: разбор увидит
    разошедшийся статус на ней, и вторая просьба была бы лишним вызовом Bot API."""
    user = await _user(db_session, 300_106, "ticket96")
    staff = await _user(db_session, 300_107, "ticket97")
    service = _service(db_session)
    ticket = await service.open(user.id, "вопрос")
    await db_session.commit()

    await service.reply_from_admin(ticket.id, "ответ", author_user_id=staff.id)
    await db_session.commit()

    payloads = list(
        (
            await db_session.scalars(
                select(OutboxMessage.payload).where(OutboxMessage.topic == TOPIC_SUPPORT_OUTBOUND)
            )
        ).all()
    )
    assert [bool(item.get("sync")) for item in payloads] == [False, False]


async def test_admin_reply_notifies_the_person_and_shows_up_in_the_topic(
    db_session: AsyncSession,
) -> None:
    """Ответ из админки обязан попасть и к человеку, и в топик супергруппы.

    Без копии в топике коллега не увидит, что обращение уже разобрано, и
    ответит второй раз.
    """
    user = await _user(db_session, 300_016, "ticket16")
    staff = await _user(db_session, 300_018, "ticket18")
    service = _service(db_session)
    ticket = await service.open(user.id, "не открывается")
    await db_session.commit()

    message = await service.reply_from_admin(
        ticket.id, "  Проверьте профиль  ", author_user_id=staff.id
    )
    await db_session.commit()

    assert message.author_kind is TicketAuthor.staff
    assert message.author_user_id == staff.id
    assert message.body == "Проверьте профиль"
    assert ticket.status is TicketStatus.waiting_user
    assert ticket.last_staff_message_at is not None
    kinds = list((await db_session.scalars(select(NotificationDelivery.kind))).all())
    assert kinds == ["ticket_reply"]
    queued = list(
        (
            await db_session.scalars(
                select(OutboxMessage).where(OutboxMessage.topic == TOPIC_SUPPORT_OUTBOUND)
            )
        ).all()
    )
    assert [item.payload["body"] for item in queued] == [
        "не открывается",
        f"{ADMIN_REPLY_MARK}\nПроверьте профиль",
    ]


async def test_admin_reply_to_a_closed_ticket_is_refused(db_session: AsyncSession) -> None:
    """Топик закрытого обращения уже закрыт: сообщение туда не дойдёт."""
    user = await _user(db_session, 300_017, "ticket17")
    staff = await _user(db_session, 300_019, "ticket19")
    service = _service(db_session)
    ticket = await service.open(user.id, "не открывается")
    await service.close(ticket.id, by_staff=True, notify=False)
    await db_session.commit()

    with pytest.raises(ServiceError) as refusal:
        await service.reply_from_admin(ticket.id, "ещё раз", author_user_id=staff.id)

    assert refusal.value.code == "ticket_closed"


async def test_message_from_an_unknown_topic_is_dropped(db_session: AsyncSession) -> None:
    """Посторонняя тема в супергруппе не должна порождать переписку из воздуха."""
    dropped = await _service(db_session).reply_from_staff(
        999_999, "привет", telegram_id=777, message_id=1
    )
    await db_session.commit()

    assert dropped is None
    assert (await db_session.scalars(select(TicketMessage))).all() == []
    assert (await db_session.scalars(select(NotificationDelivery))).all() == []


async def test_user_reply_returns_the_turn_to_staff(db_session: AsyncSession) -> None:
    """Ответ человека снова ставит обращение в очередь персонала."""
    user = await _user(db_session, 300_007, "ticket07")
    service = _service(db_session)
    ticket = await service.open(user.id, "не открывается")
    ticket.telegram_topic_id = 600
    ticket.status = TicketStatus.waiting_user
    await db_session.commit()

    message = await service.reply_from_user(user.id, ticket.id, "всё ещё не работает")
    await db_session.commit()

    assert message.author_kind is TicketAuthor.user
    assert ticket.status is TicketStatus.waiting_staff
    queued = (await db_session.scalars(select(OutboxMessage))).all()
    assert [item.payload["body"] for item in queued] == ["не открывается", "всё ещё не работает"]


async def test_reply_to_a_foreign_ticket_is_refused(db_session: AsyncSession) -> None:
    """Чужой номер обращения иначе дописывал бы в чужую переписку."""
    owner = await _user(db_session, 300_008, "ticket08")
    stranger = await _user(db_session, 300_009, "ticket09")
    service = _service(db_session)
    ticket = await service.open(owner.id, "не открывается")
    await db_session.commit()

    with pytest.raises(ServiceError) as refusal:
        await service.reply_from_user(stranger.id, ticket.id, "а покажите")

    assert refusal.value.code == "not_found"


async def test_reply_to_a_closed_ticket_is_refused(db_session: AsyncSession) -> None:
    """Топик закрытого обращения в супергруппе уже закрыт: сообщение туда не дойдёт."""
    user = await _user(db_session, 300_013, "ticket13")
    service = _service(db_session)
    ticket = await service.open(user.id, "не открывается")
    await service.close(ticket.id, by_staff=False, notify=False)
    await db_session.commit()

    with pytest.raises(ServiceError) as refusal:
        await service.reply_from_user(user.id, ticket.id, "ещё вопрос")

    assert refusal.value.code == "ticket_closed"


async def test_close_marks_the_ticket_and_queues_topic_closing(db_session: AsyncSession) -> None:
    """Закрытое обращение обязано закрыть и топик: иначе список тем растёт вечно."""
    user = await _user(db_session, 300_014, "ticket14")
    service = _service(db_session)
    ticket = await service.open(user.id, "не открывается")
    await db_session.commit()

    await service.close(ticket.id, by_staff=True, notify=False)
    await db_session.commit()

    assert ticket.status is TicketStatus.closed
    assert ticket.closed_at is not None
    queued = (await db_session.scalars(select(OutboxMessage))).all()
    assert [bool(item.payload.get("close")) for item in queued] == [False, True]
    thread = await service.thread(ticket.id)
    assert [message.author_kind for message in thread] == [
        TicketAuthor.user,
        TicketAuthor.system,
    ]


async def test_staff_closing_tells_the_person(db_session: AsyncSession) -> None:
    """Иначе человек узнаёт о закрытии, только заглянув в кабинет."""
    user = await _user(db_session, 300_101, "ticket91")
    service = _service(db_session)
    ticket = await service.open(user.id, "вопрос")
    await db_session.commit()

    await service.close(ticket.id, by_staff=True, notify=True)
    await db_session.commit()

    kinds = list((await db_session.scalars(select(NotificationDelivery.kind))).all())
    assert "ticket_closed" in kinds


async def test_silent_closing_stays_silent(db_session: AsyncSession) -> None:
    """Тихое закрытие для случая, когда разговор кончился ничем."""
    user = await _user(db_session, 300_102, "ticket92")
    service = _service(db_session)
    ticket = await service.open(user.id, "вопрос")
    await db_session.commit()

    await service.close(ticket.id, by_staff=True, notify=False)
    await db_session.commit()

    kinds = list((await db_session.scalars(select(NotificationDelivery.kind))).all())
    assert "ticket_closed" not in kinds


async def test_closing_twice_notifies_once(db_session: AsyncSession) -> None:
    """Повтор безобиден и обязан таким остаться: второе «обращение закрыто»
    человеку сказать нечего."""
    user = await _user(db_session, 300_108, "ticket98")
    service = _service(db_session)
    ticket = await service.open(user.id, "вопрос")
    await db_session.commit()

    await service.close(ticket.id, by_staff=True, notify=True)
    await service.close(ticket.id, by_staff=True, notify=True)
    await db_session.commit()

    kinds = list((await db_session.scalars(select(NotificationDelivery.kind))).all())
    assert kinds.count("ticket_closed") == 1


async def test_thread_and_list_are_ordered_for_reading(db_session: AsyncSession) -> None:
    """Переписка читается сверху вниз, а список обращений — свежими вперёд."""
    user = await _user(db_session, 300_015, "ticket15")
    service = _service(db_session)
    first = await service.open(user.id, "первое")
    second = await service.open(user.id, "второе")
    await db_session.commit()
    await service.reply_from_user(user.id, first.id, "дополнение")
    await db_session.commit()

    assert [ticket.id for ticket in await service.list_for_user(user.id)] == [second.id, first.id]
    assert [message.body for message in await service.thread(first.id)] == ["первое", "дополнение"]


async def test_one_topic_belongs_to_one_ticket(db_session: AsyncSession) -> None:
    """Ответ сотрудника ищется по топику, и второй тикет с тем же номером
    молча увёл бы его чужому человеку.

    Схема обязана это запрещать: сервис ищет через scalar(), и при двух
    совпадениях он возьмёт первый попавшийся, не заметив неоднозначности.
    Пустое поле при этом обычное дело — топик появляется после создания.
    """
    people = []
    for index in range(2):
        user = User(email=None, telegram_id=310_100 + index, referral_code=f"tickdup{index}")
        db_session.add(user)
        people.append(user)
    await db_session.flush()
    for user in people:
        db_session.add(
            Ticket(
                user_id=user.id,
                status=TicketStatus.waiting_staff,
                subject="Один топик на двоих",
                telegram_topic_id=4242,
            )
        )

    with pytest.raises(IntegrityError):
        await db_session.commit()
