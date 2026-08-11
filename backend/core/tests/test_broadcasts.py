"""Рассылки: сегменты, фиксация аудитории, темп и отмена."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    Broadcast,
    BroadcastRecipient,
    BroadcastStatus,
    OrderStatus,
    Plan,
    RecipientStatus,
    Subscription,
    SubscriptionSource,
    TrafficResetStrategy,
    User,
    UserStatus,
)
from repibot_core.db.repositories.orders import OrderRepository
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.integrations.email.sender import LoggingEmailSender
from repibot_core.services.broadcasts import BroadcastService
from repibot_core.services.errors import ServiceError
from repibot_core.services.segments import count_segment, segment_query
from repibot_core.services.unsubscribe import CALLBACK_DATA
from repibot_core.settings import Settings, get_settings

pytestmark = pytest.mark.docker

# Тот же сквад, что перечисляют тарифы в остальных наборах: тариф здесь нужен
# лишь как якорь подписки, а не как проверка витрины.
SQUAD_UUID = "11111111-1111-4111-8111-111111111111"


async def _plan(session: AsyncSession, *, code: str, is_trial: bool = False) -> Plan:
    """Тариф по коду, один на все вызовы теста.

    Код тарифа уникален, а сегмент «по тарифу» требует нескольких подписчиков
    на одном тарифе — поэтому не создание, а получение существующего.
    """
    existing = await PlanRepository(session).get_by_code(code)
    if existing is not None:
        return existing
    return await PlanRepository(session).create(
        code=code,
        name={"ru": code, "en": code},
        description=None,
        duration_days=30,
        price_rub=Decimal("300.00"),
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=3,
        internal_squad_uuids=[SQUAD_UUID],
        is_trial=is_trial,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )


async def _subscriber(
    session: AsyncSession,
    *,
    telegram_id: int,
    expired: bool,
    plan_code: str = "bcbase",
    is_trial: bool = False,
) -> User:
    """Человек с подпиской в заданном состоянии.

    Подписка ставится напрямую, а не через покупку: сегменты смотрят на её
    статус, и путь через оплату делал бы падение платежей падением ещё и здесь.
    """
    plan = await _plan(session, code=plan_code, is_trial=is_trial)
    user = User(email=None, telegram_id=telegram_id, referral_code=f"bc{telegram_id}")
    session.add(user)
    await session.flush()
    now = datetime.now(UTC)
    session.add(
        Subscription(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionState.expired if expired else SubscriptionState.active,
            started_at=now - timedelta(days=30),
            expires_at=now - timedelta(days=1) if expired else now + timedelta(days=29),
            source=SubscriptionSource.purchase,
        )
    )
    await session.flush()
    return user


async def test_one_person_gets_a_campaign_once(db_session: AsyncSession) -> None:
    """Повторный запуск материализации не должен слать письмо дважды."""
    admin = User(email=None, telegram_id=400_001, referral_code="bcadmin1")
    db_session.add(admin)
    await db_session.flush()
    campaign = Broadcast(
        created_by_user_id=admin.id,
        segment="all",
        title={"ru": "Новость", "en": "News"},
        body={"ru": "Текст", "en": "Text"},
        status=BroadcastStatus.draft,
    )
    db_session.add(campaign)
    await db_session.flush()
    for _ in range(2):
        db_session.add(
            BroadcastRecipient(
                broadcast_id=campaign.id,
                user_id=admin.id,
                channel="telegram",
                recipient="400001",
                language="ru",
                status=RecipientStatus.pending,
            )
        )

    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_segments_pick_the_right_people(db_session: AsyncSession) -> None:
    """Каждый сегмент — именованный запрос под своим тестом.

    Ошибка в сегменте — это письмо не тем людям, и её нельзя увидеть иначе
    как отдельной проверкой на каждый.
    """
    await _subscriber(db_session, telegram_id=400_010, expired=False)
    await _subscriber(db_session, telegram_id=400_011, expired=True)
    db_session.add(User(email=None, telegram_id=400_012, referral_code="bcsilent"))
    await db_session.commit()

    everyone = await count_segment(db_session, "all")
    with_access = await count_segment(db_session, "active")
    lapsed_count = await count_segment(db_session, "expired")

    assert everyone == 3
    assert with_access == 1
    assert lapsed_count == 1


async def test_trial_segment_holds_only_people_on_a_trial_plan(db_session: AsyncSession) -> None:
    """Предложение продлить триал, ушедшее платящим, — это письмо не тем людям."""
    await _subscriber(db_session, telegram_id=400_014, expired=False, plan_code="bcpaid")
    await _subscriber(
        db_session, telegram_id=400_015, expired=False, plan_code="bctrial", is_trial=True
    )
    await db_session.commit()

    assert await count_segment(db_session, "trial") == 1


async def test_never_paid_segment_drops_anyone_with_a_fulfilled_order(
    db_session: AsyncSession,
) -> None:
    """Сегмент «ни разу не платившие» смотрит на закрытые заказы, а не на подписку.

    Подписку можно получить подарком и триалом; деньги видны только по заказу.
    """
    plan = await _plan(db_session, code="bcpaid")
    payer = User(email=None, telegram_id=400_016, referral_code="bcpay016")
    freeloader = User(email=None, telegram_id=400_017, referral_code="bcpay017")
    db_session.add_all([payer, freeloader])
    await db_session.flush()
    order = await OrderRepository(db_session).create_pending(
        user_id=payer.id,
        plan=plan,
        client_key="bc-never-paid",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    order.status = OrderStatus.fulfilled
    await db_session.commit()

    assert await count_segment(db_session, "never_paid") == 1


async def test_plan_segment_holds_only_subscribers_of_that_plan(db_session: AsyncSession) -> None:
    """Имён тарифов заранее не знает никто, поэтому сегмент задан префиксом."""
    await _subscriber(db_session, telegram_id=400_018, expired=False, plan_code="bcmonth")
    await _subscriber(db_session, telegram_id=400_019, expired=False, plan_code="bcyear")
    await db_session.commit()

    assert await count_segment(db_session, "plan:bcmonth") == 1
    assert await count_segment(db_session, "plan:bcyear") == 1


async def test_opted_out_person_is_out_of_every_segment(db_session: AsyncSession) -> None:
    """Отписка обязана действовать на все рассылки, а не на те, что вспомнили."""
    user = User(email=None, telegram_id=400_013, referral_code="bcout01")
    user.marketing_opt_out_at = datetime.now(UTC)
    db_session.add(user)
    await db_session.commit()

    assert await count_segment(db_session, "all") == 0


async def test_person_without_a_channel_is_out(db_session: AsyncSession) -> None:
    """Непроверенная почта без Telegram — это адрес, которого у нас нет."""
    db_session.add(User(email="unverified@example.org", referral_code="bcnoch1"))
    await db_session.commit()

    assert await count_segment(db_session, "all") == 0


async def test_banned_person_is_out_of_every_segment(db_session: AsyncSession) -> None:
    """Заблокированному аккаунту нечего предлагать.

    Доступа у него нет и не будет, пока блокировка держится, так что письмо
    зовёт его туда, куда его не пустят. Отписаться он при этом не отписывался,
    и без отдельного фильтра попал бы в каждую рассылку.
    """
    db_session.add(User(telegram_id=400_014, referral_code="bcban01", status=UserStatus.banned))
    await db_session.commit()

    assert await count_segment(db_session, "all") == 0


async def test_segment_columns_are_addressed_by_name(db_session: AsyncSession) -> None:
    """Колонки сегмента — именованные, и материализация берёт их по имени.

    Порядковый доступ сломался бы от любой перестановки полей, молча отправив
    рассылку по языкам вместо адресов.
    """
    db_session.add(
        User(
            email="verified@example.org",
            email_verified_at=datetime.now(UTC),
            referral_code="bcmail1",
            language="en",
        )
    )
    await db_session.commit()

    row = (await db_session.execute(segment_query("all"))).mappings().one()

    assert row["channel"] == "email"
    assert row["recipient"] == "verified@example.org"
    assert row["language"] == "en"


async def test_telegram_wins_over_verified_email(db_session: AsyncSession) -> None:
    """Правило маркетинга: привязанный Telegram важнее подтверждённой почты."""
    db_session.add(
        User(
            email="both@example.org",
            email_verified_at=datetime.now(UTC),
            telegram_id=400_030,
            referral_code="bcboth01",
        )
    )
    await db_session.commit()

    row = (await db_session.execute(segment_query("all"))).mappings().one()

    assert (row["channel"], row["recipient"]) == ("telegram", "400030")


def test_unknown_segment_is_refused_by_name() -> None:
    """Опечатка в имени сегмента обязана падать, а не отправлять письмо всей базе."""
    with pytest.raises(KeyError):
        segment_query("everyone")


async def test_start_freezes_the_audience(db_session: AsyncSession) -> None:
    """Счётчик «отправлено 3400 из 5000» честен только при зафиксированной аудитории."""
    admin = User(email=None, telegram_id=400_020, referral_code="bcadm020")
    db_session.add(admin)
    await db_session.flush()
    await db_session.commit()
    service = BroadcastService(db_session)
    campaign = await service.create(
        created_by=admin.id,
        segment="all",
        title={"ru": "Новость", "en": "News"},
        body={"ru": "Текст", "en": "Text"},
    )
    await db_session.commit()

    planned = await service.start(campaign.id)
    db_session.add(User(email=None, telegram_id=400_021, referral_code="bclate01"))
    await db_session.commit()

    recipients = await db_session.scalar(
        select(func.count())
        .select_from(BroadcastRecipient)
        .where(BroadcastRecipient.broadcast_id == campaign.id)
    )
    assert planned == 1
    assert recipients == 1
    assert campaign.status is BroadcastStatus.running


async def test_start_is_idempotent(db_session: AsyncSession) -> None:
    """Двойной клик по кнопке запуска не должен удваивать рассылку."""
    admin = User(email=None, telegram_id=400_022, referral_code="bcadm022")
    db_session.add(admin)
    await db_session.flush()
    await db_session.commit()
    service = BroadcastService(db_session)
    campaign = await service.create(
        created_by=admin.id,
        segment="all",
        title={"ru": "Новость", "en": "News"},
        body={"ru": "Текст", "en": "Text"},
    )
    await db_session.commit()
    await service.start(campaign.id)

    with pytest.raises(ServiceError) as second:
        await service.start(campaign.id)

    assert second.value.code == "broadcast_not_draft"


async def test_only_one_campaign_runs_at_a_time(db_session: AsyncSession) -> None:
    """Две одновременные кампании делят лимит Telegram и обе идут вдвое дольше."""
    admin = User(email=None, telegram_id=400_023, referral_code="bcadm023")
    db_session.add(admin)
    await db_session.flush()
    await db_session.commit()
    service = BroadcastService(db_session)
    first = await service.create(
        created_by=admin.id, segment="all", title={"ru": "1"}, body={"ru": "1"}
    )
    second = await service.create(
        created_by=admin.id, segment="all", title={"ru": "2"}, body={"ru": "2"}
    )
    await db_session.commit()
    await service.start(first.id)

    with pytest.raises(ServiceError) as refusal:
        await service.start(second.id)

    assert refusal.value.code == "broadcast_busy"


async def test_draft_on_an_unknown_segment_is_refused(db_session: AsyncSession) -> None:
    """Имя сегмента проверяется при создании, а не при запуске.

    Черновик с опечаткой дожил бы до кнопки «Отправить» и упал бы там, где
    администратор уже уверен, что кампания готова.
    """
    admin = User(email=None, telegram_id=400_024, referral_code="bcadm024")
    db_session.add(admin)
    await db_session.flush()
    await db_session.commit()

    with pytest.raises(ServiceError) as refusal:
        await BroadcastService(db_session).create(
            created_by=admin.id, segment="everyone", title={"ru": "1"}, body={"ru": "1"}
        )

    assert refusal.value.code == "unknown_segment"


class FakeTelegram:
    """Двойник узкого протокола отправки, а не всего BotApi.

    Клиент целиком потянул бы за собой Valkey и http-клиент ради одного
    сообщения; сервису из него нужен ровно один метод.
    """

    def __init__(self, fail_on: int | None = None) -> None:
        self.sent: list[tuple[int, str, dict[str, object] | None]] = []
        self._fail_on = fail_on
        self._calls = 0

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict[str, object] | None = None
    ) -> None:
        current = self._calls
        self._calls += 1
        if current == self._fail_on:
            msg = "бот заблокирован получателем"
            raise RuntimeError(msg)
        self.sent.append((chat_id, text, reply_markup))


def _fast_settings() -> Settings:
    """Предельный допустимый темп: тест не должен ждать секунды на паузах.

    Задержка при этом остаётся — выдержка темпа и есть проверяемое поведение,
    просто на тридцати сообщениях в секунду она равна 33 мс на получателя.
    """
    return get_settings().model_copy(update={"broadcast_rate_per_second": 30})


async def _launched(
    session: AsyncSession,
    *,
    created_by: int,
    body: dict[str, str] | None = None,
) -> tuple[Broadcast, BroadcastService]:
    """Кампания на сегмент «все», уже переведённая в работу."""
    service = BroadcastService(session, _fast_settings())
    campaign = await service.create(
        created_by=created_by,
        segment="all",
        title={"ru": "Новость", "en": "News"},
        body=body if body is not None else {"ru": "Текст", "en": "Text"},
    )
    await session.commit()
    await service.start(campaign.id)
    return campaign, service


async def _running_campaign(
    session: AsyncSession, *, people: int
) -> tuple[Broadcast, BroadcastService]:
    """Идущая кампания на заданное число получателей в Telegram.

    Автор кампании — первый же из них: отдельный администратор сам попал бы в
    сегмент «все» и сдвинул бы число получателей на единицу.
    """
    people_created: list[User] = []
    for index in range(people):
        person = User(email=None, telegram_id=401_000 + index, referral_code=f"bcrun{index:03d}")
        session.add(person)
        people_created.append(person)
    await session.flush()
    await session.commit()
    return await _launched(session, created_by=people_created[0].id)


async def test_cancel_stops_the_campaign_between_batches(db_session: AsyncSession) -> None:
    """Остановить кампанию — единственный способ исправить ошибку в тексте.

    Отправленное не отзывается; всё, что можно спасти, — остаток аудитории.
    """
    campaign, service = await _running_campaign(db_session, people=5)
    sender = FakeTelegram()

    await service.send_batch(telegram=sender, email=None, limit=2)
    await service.cancel(campaign.id)
    after_cancel = await service.send_batch(telegram=sender, email=None, limit=10)
    await db_session.commit()

    assert len(sender.sent) == 2
    assert after_cancel == 0
    assert campaign.status is BroadcastStatus.canceled


async def test_cancel_stops_inside_a_batch(db_session: AsyncSession) -> None:
    """Отмена обязана останавливать рассылку в пределах секунд, а не пачки.

    Проверка между пачками означала бы, что после нажатия «Отменить» уходит
    ещё вся текущая пачка — при темпе в 25 в секунду это полторы тысячи писем.
    """
    campaign, service = await _running_campaign(db_session, people=5)

    class CancelingTelegram:
        """Отменяет кампанию чужой рукой прямо посреди пачки."""

        def __init__(self) -> None:
            self.sent: list[int] = []

        async def send_message(
            self, chat_id: int, text: str, reply_markup: dict[str, object] | None = None
        ) -> None:
            self.sent.append(chat_id)
            await db_session.execute(
                update(Broadcast)
                .where(Broadcast.id == campaign.id)
                .values(status=BroadcastStatus.canceled)
            )

    sender = CancelingTelegram()

    await service.send_batch(telegram=sender, email=None, limit=5)
    await db_session.commit()

    assert len(sender.sent) == 1
    assert campaign.status is not BroadcastStatus.done


async def test_failed_recipient_does_not_stop_the_rest(db_session: AsyncSession) -> None:
    """Один заблокировавший бота человек не должен обрывать рассылку на всех."""
    campaign, service = await _running_campaign(db_session, people=3)
    sender = FakeTelegram(fail_on=1)

    await service.send_batch(telegram=sender, email=None, limit=10)
    await db_session.commit()

    error = await db_session.scalar(
        select(BroadcastRecipient.error).where(
            BroadcastRecipient.broadcast_id == campaign.id,
            BroadcastRecipient.status == RecipientStatus.failed,
        )
    )
    assert (campaign.sent_count, campaign.failed_count) == (2, 1)
    assert campaign.status is BroadcastStatus.done
    assert error


async def test_telegram_message_carries_an_unsubscribe_button(db_session: AsyncSession) -> None:
    """Отписка обязана быть на расстоянии одного касания.

    Без неё человек блокирует бота, и вместе с предложениями теряются
    сообщения об оплате и об окончании подписки, отключить которые он не просил.
    """
    campaign, service = await _running_campaign(db_session, people=1)
    sender = FakeTelegram()

    await service.send_batch(telegram=sender, email=None, limit=1)
    await db_session.commit()

    _, text, markup = sender.sent[0]
    assert markup is not None
    keyboard = markup["inline_keyboard"]
    assert isinstance(keyboard, list)
    assert keyboard[0][0]["callback_data"] == CALLBACK_DATA
    assert campaign.body["ru"] in text


async def test_email_recipient_gets_a_link_to_unsubscribe(db_session: AsyncSession) -> None:
    """Письмо без отписки — жалоба на спам, а следом падение доставляемости.

    Почтовый провайдер понижает домен целиком, вместе с чеками об оплате,
    поэтому ссылка обязана быть под каждым маркетинговым письмом.
    """
    reader = User(
        email="reader@example.org",
        email_verified_at=datetime.now(UTC),
        referral_code="bcmail2",
    )
    db_session.add(reader)
    await db_session.flush()
    await db_session.commit()
    campaign, service = await _launched(db_session, created_by=reader.id)
    sender = LoggingEmailSender()

    await service.send_batch(telegram=None, email=sender, limit=1)
    await db_session.commit()

    assert len(sender.sent) == 1
    assert "/unsubscribe?token=" in sender.sent[0].text
    assert sender.sent[0].subject == "Новость"
    assert campaign.sent_count == 1


async def test_text_falls_back_to_russian(db_session: AsyncSession) -> None:
    """Языка получателя может не быть в кампании — тогда русский, а не пустота.

    Пустое сообщение Telegram просто отвергнет, и вся англоязычная часть базы
    оказалась бы в неудачах на ровном месте.
    """
    person = User(email=None, telegram_id=401_500, referral_code="bclang1", language="en")
    db_session.add(person)
    await db_session.flush()
    await db_session.commit()
    _, service = await _launched(db_session, created_by=person.id, body={"ru": "Только так"})
    sender = FakeTelegram()

    await service.send_batch(telegram=sender, email=None, limit=1)
    await db_session.commit()

    # Проверяется откат языка, а не состав сообщения: заголовок идёт первой
    # строкой, и точное равенство здесь ломалось бы от любой правки вёрстки.
    assert "Только так" in sender.sent[0][1]


async def test_telegram_recipient_sees_the_campaign_title(db_session: AsyncSession) -> None:
    """Заголовок обязан дойти до всех, а не до одних почтовых адресатов.

    В письме он становится темой, а у сообщения в Telegram темы нет — и без
    первой строки половина аудитории не увидела бы того, что админ написал
    в поле «заголовок», а сам админ об этом даже не узнал бы.
    """
    campaign, service = await _running_campaign(db_session, people=1)
    sender = FakeTelegram()

    await service.send_batch(telegram=sender, email=None, limit=1)
    await db_session.commit()

    _, text, _ = sender.sent[0]
    assert text.startswith(campaign.title["ru"])
    assert campaign.body["ru"] in text
