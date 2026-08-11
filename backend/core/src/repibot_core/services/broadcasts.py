"""Жизнь кампании: черновик, запуск с фиксацией аудитории, отмена.

Кампании выполняются строго по одной. Две одновременные поделили бы лимит
Telegram и обе шли бы вдвое дольше, а порядок их завершения стал бы
непредсказуемым — поэтому запуск при уже идущей отвергается.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import cast, func, insert, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Broadcast, BroadcastRecipient, BroadcastStatus, RecipientStatus
from repibot_core.services.errors import ServiceError
from repibot_core.services.segments import PLAN_PREFIX, SEGMENTS, segment_query
from repibot_core.settings import Settings, get_settings

# Русский обязателен, остальные языки — по желанию: он же и запасной текст при
# отправке, и без него получателю с чужим языком уходило бы пустое письмо.
FALLBACK_LANGUAGE = "ru"


class BroadcastService:
    """Один вход для админского API и задачи отправки."""

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()

    async def create(
        self,
        *,
        created_by: int,
        segment: str,
        title: dict[str, str],
        body: dict[str, str],
    ) -> Broadcast:
        """Черновик кампании. Транзакцию закрывает вызывающий.

        Имя сегмента и тексты проверяются здесь, а не при запуске: черновик с
        опечаткой дожил бы до кнопки «Отправить» и упал бы там, где
        администратор уже уверен, что кампания готова.
        """
        if not (segment in SEGMENTS or segment.startswith(PLAN_PREFIX)):
            raise ServiceError(f"неизвестный сегмент: {segment}", "unknown_segment")
        if not title.get(FALLBACK_LANGUAGE) or not body.get(FALLBACK_LANGUAGE):
            raise ServiceError("нужны заголовок и текст на русском", "broadcast_text_required")

        campaign = Broadcast(
            created_by_user_id=created_by,
            segment=segment,
            title=title,
            body=body,
            status=BroadcastStatus.draft,
        )
        self._session.add(campaign)
        await self._session.flush()
        return campaign

    async def start(self, broadcast_id: int) -> int:
        """Фиксирует аудиторию одним запросом и переводит кампанию в работу.

        INSERT ... SELECT, а не выборка в Python и вставка по одному: пять
        тысяч отдельных вставок — это пять тысяч обращений к базе, и любое
        падение посреди оставило бы половину аудитории.
        """
        async with self._session.begin():
            campaign = await self._session.get(Broadcast, broadcast_id, with_for_update=True)
            if campaign is None:
                raise ServiceError("рассылка не найдена", "not_found")
            if campaign.status is not BroadcastStatus.draft:
                raise ServiceError("рассылка уже запущена", "broadcast_not_draft")
            running = await self._session.scalar(
                select(Broadcast.id).where(Broadcast.status == BroadcastStatus.running).limit(1)
            )
            if running is not None:
                raise ServiceError("уже идёт другая рассылка", "broadcast_busy")

            # Колонки подзапроса берутся по именам, которые segments._base()
            # задаёт через label(): порядковый доступ сломался бы от любой
            # перестановки полей, молча отправив рассылку по языкам.
            source = segment_query(campaign.segment).subquery()
            await self._session.execute(
                insert(BroadcastRecipient).from_select(
                    ["broadcast_id", "user_id", "channel", "recipient", "language", "status"],
                    select(
                        literal(campaign.id),
                        source.c.user_id,
                        source.c.channel,
                        source.c.recipient,
                        source.c.language,
                        # Явное приведение к перечислению: без него Postgres
                        # получил бы в колонку типа broadcast_recipient_status
                        # обычную строку и отверг бы всю вставку.
                        cast(
                            literal(RecipientStatus.pending.value),
                            BroadcastRecipient.status.type,
                        ),
                    ),
                )
            )
            planned = await self._session.scalar(
                select(func.count())
                .select_from(BroadcastRecipient)
                .where(BroadcastRecipient.broadcast_id == campaign.id)
            )
            campaign.planned_count = int(planned or 0)
            campaign.status = BroadcastStatus.running
            campaign.started_at = datetime.now(UTC)
        return campaign.planned_count

    async def cancel(self, broadcast_id: int) -> None:
        """Останавливает идущую кампанию. Уже отправленное не отзывается.

        Завершённая отмене не подлежит: отзывать нечего, а «отменённая» в
        журнале рядом с пятью тысячами отправленных писем прямо врала бы.
        """
        async with self._session.begin():
            campaign = await self._session.get(Broadcast, broadcast_id, with_for_update=True)
            if campaign is None:
                raise ServiceError("рассылка не найдена", "not_found")
            if campaign.status is not BroadcastStatus.running:
                raise ServiceError("рассылка не идёт", "broadcast_not_running")
            campaign.status = BroadcastStatus.canceled
            campaign.finished_at = datetime.now(UTC)

    async def list_campaigns(self) -> list[Broadcast]:
        """Свежие сверху: администратор ищет ту, что запустил только что."""
        found = await self._session.scalars(select(Broadcast).order_by(Broadcast.id.desc()))
        return list(found.all())
