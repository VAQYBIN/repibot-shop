"""Жизнь кампании: черновик, запуск с фиксацией аудитории, отмена.

Кампании выполняются строго по одной. Две одновременные поделили бы лимит
Telegram и обе шли бы вдвое дольше, а порядок их завершения стал бы
непредсказуемым — поэтому запуск при уже идущей отвергается.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import cast, func, insert, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Broadcast, BroadcastRecipient, BroadcastStatus, RecipientStatus
from repibot_core.i18n import translate
from repibot_core.integrations.email.sender import EmailSender
from repibot_core.integrations.email.templates import render_notification
from repibot_core.services.errors import ServiceError
from repibot_core.services.segments import PLAN_PREFIX, SEGMENTS, segment_query
from repibot_core.services.unsubscribe import CALLBACK_DATA, sign_unsubscribe_token
from repibot_core.settings import Settings, get_settings

# Русский обязателен, остальные языки — по желанию: он же и запасной текст при
# отправке, и без него получателю с чужим языком уходило бы пустое письмо.
FALLBACK_LANGUAGE = "ru"

CHANNEL_TELEGRAM = "telegram"
# Длина колонки `error`: обрезаем сами, иначе многословная ошибка провайдера
# уронит всю вставку строки получателя, и причина неудачи потеряется целиком.
ERROR_LIMIT = 512


class TelegramSender(Protocol):
    """Ровно та часть Bot API, которой пользуется рассылка.

    Не весь `BotApi`: сервис не должен зависеть от клиента целиком, иначе
    тест ради одного сообщения собирал бы Valkey и http-клиент.
    """

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict[str, object] | None = None
    ) -> None: ...


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

    async def send_batch(
        self,
        *,
        telegram: TelegramSender | None,
        email: EmailSender | None,
        limit: int | None = None,
    ) -> int:
        """Отправляет пачку получателей текущей кампании, выдерживая темп.

        Темп держится задержкой между отправками, а не окном подсчёта: задача
        идёт раз в минуту, окно между её запусками всё равно обнулилось бы, а
        Telegram считает секунды, а не минуты.
        """
        rate = self._settings.broadcast_rate_per_second
        # Умолчание — сколько успевает уйти за минуту до следующего прогона:
        # брать больше значило бы держать одну задачу дольше её расписания.
        size = limit if limit is not None else rate * 60
        campaign = await self._current_running()
        if campaign is None:
            # Даже поиск кампании открыл транзакцию, и оставленная открытой она
            # держала бы соединение в idle in transaction между прогонами.
            await self._session.commit()
            return 0
        pause = 1.0 / rate

        rows = list(
            (
                await self._session.scalars(
                    select(BroadcastRecipient)
                    .where(
                        BroadcastRecipient.broadcast_id == campaign.id,
                        BroadcastRecipient.status == RecipientStatus.pending,
                    )
                    .order_by(BroadcastRecipient.id)
                    .limit(size)
                )
            ).all()
        )
        sent = 0
        for row in rows:
            # Статус перечитывается на каждом получателе, а не между пачками:
            # отмена обязана останавливать кампанию в пределах секунд, иначе
            # после нажатия «Отменить» уходит ещё вся текущая пачка.
            await self._session.refresh(campaign, ["status"])
            if campaign.status is not BroadcastStatus.running:
                break
            try:
                await self._deliver(row, campaign, telegram=telegram, email=email)
            except Exception as error:
                # Неудача одного получателя остаётся в его строке: один
                # заблокировавший бота человек не должен обрывать рассылку
                # на всех остальных.
                row.status = RecipientStatus.failed
                row.error = str(error)[:ERROR_LIMIT] or type(error).__name__
                campaign.failed_count += 1
            else:
                row.status = RecipientStatus.sent
                row.sent_at = datetime.now(UTC)
                campaign.sent_count += 1
                sent += 1
            # Каждый получатель фиксируется отдельно: падение процесса посреди
            # пачки иначе повторило бы всё, что уже ушло.
            await self._session.commit()
            await asyncio.sleep(pause)

        remaining = await self._session.scalar(
            select(func.count())
            .select_from(BroadcastRecipient)
            .where(
                BroadcastRecipient.broadcast_id == campaign.id,
                BroadcastRecipient.status == RecipientStatus.pending,
            )
        )
        # Отменённая кампания завершённой не становится: в журнале «done»
        # рядом с недоотправленной аудиторией прямо врал бы.
        if not remaining and campaign.status is BroadcastStatus.running:
            campaign.status = BroadcastStatus.done
            campaign.finished_at = datetime.now(UTC)
        # Транзакция закрывается в любом случае, даже когда писать нечего:
        # иначе сессия остаётся с начатой транзакцией, и следующая же операция
        # вызывающего — та же отмена кампании — падает на её открытии.
        await self._session.commit()
        return sent

    async def _current_running(self) -> Broadcast | None:
        """Единственная идущая кампания — их по одной, поэтому limit(1) честен."""
        found: Broadcast | None = await self._session.scalar(
            select(Broadcast).where(Broadcast.status == BroadcastStatus.running).limit(1)
        )
        return found

    async def _deliver(
        self,
        row: BroadcastRecipient,
        campaign: Broadcast,
        *,
        telegram: TelegramSender | None,
        email: EmailSender | None,
    ) -> None:
        """Отправляет одному получателю по зафиксированному за ним каналу."""
        # Язык получателя с откатом на русский: тексты на всех языках писать
        # необязательно, а пустое сообщение Telegram просто отвергнет — и вся
        # англоязычная часть базы оказалась бы в неудачах на ровном месте.
        body = campaign.body.get(row.language) or campaign.body[FALLBACK_LANGUAGE]
        subject = campaign.title.get(row.language) or campaign.title[FALLBACK_LANGUAGE]

        if row.channel == CHANNEL_TELEGRAM:
            if telegram is None:
                msg = "клиент бота не передан рассылке"
                raise RuntimeError(msg)
            # Отписка обязана быть на расстоянии одного касания: без неё
            # человек блокирует бота, и вместе с предложениями теряются
            # сообщения об оплате и об окончании подписки.
            markup: dict[str, object] = {
                "inline_keyboard": [
                    [
                        {
                            "text": translate(row.language, "notify.unsubscribe"),
                            "callback_data": CALLBACK_DATA,
                        }
                    ]
                ]
            }
            # Заголовок первой строкой: в письме он становится темой, а у
            # сообщения в Telegram темы нет, и без него половина аудитории не
            # увидела бы того, что админ написал в поле «заголовок».
            # Без parse_mode: текст кампании пишет человек, и случайное
            # подчёркивание в нём иначе валило бы отправку разбором разметки.
            await telegram.send_message(int(row.recipient), f"{subject}\n\n{body}", markup)
            return

        if email is None:
            msg = "отправитель почты не передан рассылке"
            raise RuntimeError(msg)
        site = self._settings.public_web_url.rstrip("/")
        # Ссылка отписки в каждом маркетинговом письме — требование закона и
        # условие доставляемости: без неё отказываются кнопкой «спам», и
        # почтовый провайдер понижает весь домен, включая чеки об оплате.
        token = sign_unsubscribe_token(row.user_id)
        text = (
            body
            + "\n\n"
            + translate(
                row.language, "notify.unsubscribe_link", link=f"{site}/unsubscribe?token={token}"
            )
        )
        await email.send(
            render_notification(
                row.language, to=row.recipient, subject=subject, body=text, link=site
            )
        )
