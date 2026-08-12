"""Обращения в поддержку: одна переписка, два входа.

Внешние вызовы Telegram здесь не делаются: сервис пишет в базу и ставит
задачу в очередь. Иначе недоступная супергруппа теряла бы обращение, за
которое человек уже заплатил ожиданием.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Ticket, TicketAuthor, TicketMessage, TicketStatus
from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.services.errors import ServiceError
from repibot_core.services.notifications import NotificationService
from repibot_core.settings import Settings, get_settings

logger = logging.getLogger(__name__)

TOPIC_SUPPORT_OUTBOUND = "support.outbound"

# Тема топика — первые слова обращения: в списке тем супергруппы персонал
# должен различать обращения без открытия каждого. Заодно это предел Bot API
# на имя темы, за которым createForumTopic просто отвергает запрос.
SUBJECT_LIMIT = 120

# Метка состояния в названии темы: очередь работы читается по цвету, без
# чтения слов. Красное ждёт нас, жёлтое ждёт человека, галочка закрыта.
TOPIC_MARKS: dict[TicketStatus, str] = {
    TicketStatus.waiting_staff: "🔴",
    TicketStatus.waiting_user: "🟡",
    TicketStatus.closed: "✅",
}

# Предел Bot API на имя темы. Тема обращения хранится длиннее (SUBJECT_LIMIT),
# и вместе с меткой и номером имя иначе перестало бы приниматься.
TOPIC_NAME_LIMIT = 128

# Сколько ответа сотрудника уезжает в уведомление. Целиком — значит письмо и
# сообщение бота повторяют переписку; ссылка на неё в них и так есть.
NOTIFICATION_BODY_LIMIT = 300

# Отметки в переписке о закрытии. Не перевод, а запись в журнале обращения:
# по ней видно, кто прекратил разговор — человек или персонал.
CLOSED_BY_STAFF = "Обращение закрыто поддержкой."
CLOSED_BY_USER = "Обращение закрыто пользователем."

# Пометка ответа, отправленного из админки. В топик бот кладёт и реплики
# человека, и такие ответы одним и тем же сообщением: без пометки коллега в
# супергруппе принял бы ответ за новый вопрос и ответил бы второй раз.
ADMIN_REPLY_MARK = "Ответ из админки:"


def topic_name(ticket: Ticket) -> str:
    """Название темы: метка состояния, номер обращения, сама тема.

    Функция, а не метод сервиса: имя нужно разбору очереди, у которого своя
    сессия и своя транзакция, а сервис ему для этого не нужен.
    """
    return f"{TOPIC_MARKS[ticket.status]} #{ticket.id} {ticket.subject}"[:TOPIC_NAME_LIMIT]


class SupportService:
    """Один вход для бота, кабинета и админки."""

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._outbox = OutboxRepository(session)

    def enabled(self) -> bool:
        """Пустая супергруппа выключает поддержку целиком.

        Стенд без супергруппы обязан подниматься: маршруты и экраны спрашивают
        об этом до того, как предложить человеку написать.
        """
        return self._settings.support_chat_id is not None

    async def open(self, user_id: int, body: str) -> Ticket:
        """Новое обращение. Транзакцию закрывает вызывающий."""
        self._require_enabled()
        text = self._require_text(body)
        open_count = await self._session.scalar(
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.user_id == user_id, Ticket.status != TicketStatus.closed)
        )
        # Предел держит сервис, а не частичный уникальный индекс: индекс дал бы
        # ровно одно открытое обращение, а человеку, у которого одновременно
        # сломались оплата и доступ, этого мало.
        if int(open_count or 0) >= self._settings.ticket_max_open:
            raise ServiceError("слишком много открытых обращений", "too_many_tickets")

        ticket = Ticket(
            user_id=user_id,
            status=TicketStatus.waiting_staff,
            subject=text[:SUBJECT_LIMIT],
            last_user_message_at=datetime.now(UTC),
        )
        self._session.add(ticket)
        await self._session.flush()
        await self._add_message(ticket, TicketAuthor.user, text, author_user_id=user_id)
        # Топика ещё нет: его создаст разбор очереди и вернёт идентификатор.
        await self._enqueue(ticket, text)
        return ticket

    async def reply_from_user(self, user_id: int, ticket_id: int, body: str) -> TicketMessage:
        """Ответ человека возвращает ход персоналу."""
        self._require_enabled()
        text = self._require_text(body)
        ticket = await self._session.get(Ticket, ticket_id)
        # Чужой номер обращения неотличим от несуществующего намеренно: иначе
        # перебором номеров можно узнать, что обращение с таким номером есть.
        if ticket is None or ticket.user_id != user_id:
            raise ServiceError("обращение не найдено", "not_found")
        if ticket.status is TicketStatus.closed:
            raise ServiceError("обращение закрыто", "ticket_closed")

        message = await self._add_message(ticket, TicketAuthor.user, text, author_user_id=user_id)
        ticket.status = TicketStatus.waiting_staff
        ticket.last_user_message_at = datetime.now(UTC)
        await self._enqueue(ticket, text)
        return message

    async def reply_from_staff(
        self, topic_id: int, body: str, *, telegram_id: int, message_id: int
    ) -> TicketMessage | None:
        """Ответ из топика супергруппы. Чужая тема отбрасывается.

        Поддержка здесь не спрашивается о включённости: сообщение сотрудника
        уже написано, и терять его из-за очищенной настройки нельзя.
        """
        ticket = await self._session.scalar(
            select(Ticket).where(Ticket.telegram_topic_id == topic_id)
        )
        if ticket is None:
            # Посторонняя тема в супергруппе не должна порождать переписку с
            # несуществующим человеком: у сообщения просто нет адресата.
            logger.warning(
                "сообщение из топика без обращения отброшено", extra={"topic_id": topic_id}
            )
            return None
        text = body.strip()
        if not text:
            return None

        return await self._staff_reply(
            ticket, text, author_telegram_id=telegram_id, telegram_message_id=message_id
        )

    async def reply_from_admin(
        self, ticket_id: int, body: str, *, author_user_id: int
    ) -> TicketMessage:
        """Ответ сотрудника из админки. Транзакцию закрывает вызывающий.

        Включённость поддержки здесь не требуется по той же причине, что и в
        ответе из топика: человек уже ждёт ответа, и терять его из-за очищенной
        настройки нельзя.
        """
        text = self._require_text(body)
        ticket = await self._session.get(Ticket, ticket_id)
        if ticket is None:
            raise ServiceError("обращение не найдено", "not_found")
        if ticket.status is TicketStatus.closed:
            raise ServiceError("обращение закрыто", "ticket_closed")

        message = await self._staff_reply(ticket, text, author_user_id=author_user_id)
        # Копия уходит в топик, чтобы коллега в супергруппе видел разобранное
        # обращение. Без супергруппы очередь не разбирается вовсе, и класть в
        # неё сообщение значило бы копить вечно повторяющуюся задачу.
        if self.enabled():
            await self._enqueue(ticket, f"{ADMIN_REPLY_MARK}\n{text}")
        return message

    async def _staff_reply(
        self,
        ticket: Ticket,
        text: str,
        *,
        author_user_id: int | None = None,
        author_telegram_id: int | None = None,
        telegram_message_id: int | None = None,
    ) -> TicketMessage:
        """Общая часть обоих входов персонала: реплика, ход и сигнал человеку."""
        message = await self._add_message(
            ticket,
            TicketAuthor.staff,
            text,
            author_user_id=author_user_id,
            author_telegram_id=author_telegram_id,
            telegram_message_id=telegram_message_id,
        )
        ticket.status = TicketStatus.waiting_user
        ticket.last_staff_message_at = datetime.now(UTC)
        # Ответ обязан дойти до человека, а не остаться в топике: половина
        # плательщиков в супергруппу не заглядывает и Telegram не привязывала.
        await NotificationService(self._session).enqueue(
            user_id=ticket.user_id,
            kind="ticket_reply",
            dedup_key=f"ticket:{ticket.id}:msg:{message.id}",
            params={"body": text[:NOTIFICATION_BODY_LIMIT]},
        )
        return message

    async def close(self, ticket_id: int, *, by_staff: bool) -> None:
        """Закрывает обращение и его топик. Повтор безобиден."""
        ticket = await self._session.get(Ticket, ticket_id)
        if ticket is None:
            raise ServiceError("обращение не найдено", "not_found")
        if ticket.status is TicketStatus.closed:
            return

        ticket.status = TicketStatus.closed
        ticket.closed_at = datetime.now(UTC)
        await self._add_message(
            ticket,
            TicketAuthor.system,
            CLOSED_BY_STAFF if by_staff else CLOSED_BY_USER,
        )
        # Закрытие ставится в ту же очередь и той же темой: топик мог ещё не
        # существовать, и порядок сообщений очереди создаст его перед закрытием.
        await self._outbox.add(
            TOPIC_SUPPORT_OUTBOUND, {"ticket_id": ticket.id, "body": "", "close": True}
        )

    async def list_for_user(self, user_id: int) -> list[Ticket]:
        """Свежие сверху: человек ищет то обращение, которое только что открыл."""
        found = await self._session.scalars(
            select(Ticket).where(Ticket.user_id == user_id).order_by(Ticket.id.desc())
        )
        return list(found.all())

    async def thread(self, ticket_id: int) -> list[TicketMessage]:
        """Переписка сверху вниз.

        Номер — второй ключ сортировки: в одной транзакции `now()` у всех строк
        одинаковый, и по одному времени порядок реплик был бы случайным.
        """
        found = await self._session.scalars(
            select(TicketMessage)
            .where(TicketMessage.ticket_id == ticket_id)
            .order_by(TicketMessage.created_at, TicketMessage.id)
        )
        return list(found.all())

    async def _add_message(
        self,
        ticket: Ticket,
        author_kind: TicketAuthor,
        body: str,
        *,
        author_user_id: int | None = None,
        author_telegram_id: int | None = None,
        telegram_message_id: int | None = None,
    ) -> TicketMessage:
        message = TicketMessage(
            ticket_id=ticket.id,
            author_kind=author_kind,
            author_user_id=author_user_id,
            author_telegram_id=author_telegram_id,
            body=body,
            telegram_message_id=telegram_message_id,
        )
        self._session.add(message)
        # Ключ дедупликации сигнала строится по номеру сообщения, поэтому он
        # нужен вызывающему до конца транзакции.
        await self._session.flush()
        return message

    async def _enqueue(self, ticket: Ticket, body: str) -> None:
        await self._outbox.add(
            TOPIC_SUPPORT_OUTBOUND,
            {"ticket_id": ticket.id, "subject": ticket.subject, "body": body},
        )

    def _require_enabled(self) -> None:
        if not self.enabled():
            raise ServiceError("поддержка недоступна", "support_unavailable")

    @staticmethod
    def _require_text(body: str) -> str:
        text = body.strip()
        if not text:
            # Пустое обращение — это топик без вопроса, на который персоналу
            # нечего ответить.
            raise ServiceError("сообщение пустое", "validation_error")
        return text
