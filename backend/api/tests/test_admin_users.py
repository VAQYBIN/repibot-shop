"""Пользователи в админке: поиск, карточка, журнал и действия над человеком."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import User, UserStatus
from repibot_core.integrations.remnawave.client import RemnawaveClient
from repibot_core.testing.remnawave import BASE_URL, FakePanel

pytestmark = pytest.mark.docker

# Тот же номер, с которым входит фикстура telegram_user_headers: именно её
# аккаунт получает триал, а значит и подписку с устройствами.
TELEGRAM_SUBSCRIBER_ID = 900_003
# Номер, которого в базе заведомо нет: схема пересоздаётся на каждый тест.
MISSING_USER_ID = 999_999

NEW_SHORT_UUID = "freshshortuuid01"


async def _subscriber_id(engine: AsyncEngine) -> int:
    """Номер аккаунта, которому фикстура выдала триал."""
    async with create_session_factory(engine)() as session:
        found = await session.execute(
            select(User.id).where(User.telegram_id == TELEGRAM_SUBSCRIBER_ID)
        )
        return int(found.scalar_one())


def _panel_user_id(panel: FakePanel) -> int:
    """Триал завёл ровно одного пользователя в тестовой панели."""
    user_id = next(iter(panel.users))
    assert isinstance(user_id, int)
    return user_id


def _revoking_panel(panel: FakePanel) -> Callable[[], RemnawaveClient]:
    """Панель, умеющая выпустить новую ссылку подписки.

    Отдельной заглушкой, а не общей из ядра: этот план не даёт её трогать, а
    маршрут выпуска ссылки проверить всё равно нужно. Пользователь берётся из
    общей заглушки — он там уже есть, и ответ остаётся настоящим по форме.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        panel_id = int(request.url.path.split("/")[3])
        user = dict(panel.users[panel_id])
        user["shortUuid"] = NEW_SHORT_UUID
        user["subscriptionUrl"] = f"{BASE_URL}/sub/{NEW_SHORT_UUID}"
        panel.users[panel_id] = user
        return httpx.Response(200, json={"response": user})

    def factory() -> RemnawaveClient:
        return RemnawaveClient(
            base_url=BASE_URL,
            token="test",
            max_attempts=1,
            transport=httpx.MockTransport(handle),
        )

    return factory


# --- права ---


async def test_support_cannot_grant_days(
    api_client: AsyncClient,
    support_headers: dict[str, str],
    plain_user_id: int,
    month_plan: int,
) -> None:
    """Сотрудник, умеющий выдать себе год подписки, — это не поддержка."""
    granted = await api_client.post(
        f"/api/admin/users/{plain_user_id}/subscription",
        json={"plan_id": month_plan, "days": 365},
        headers=support_headers,
    )

    assert granted.status_code == 403


async def test_support_searches_and_blocks(
    api_client: AsyncClient, support_headers: dict[str, str], plain_user_id: int
) -> None:
    """Работа с людьми — и есть работа поддержки: список и блокировка ей открыты."""
    listed = await api_client.get(
        "/api/admin/users", params={"query": "subscriber"}, headers=support_headers
    )
    blocked = await api_client.post(
        f"/api/admin/users/{plain_user_id}/block", headers=support_headers
    )

    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [plain_user_id]
    assert blocked.status_code == 200
    assert blocked.json() == {"changed": True}


async def test_support_may_unlink_a_device(
    api_client: AsyncClient,
    support_headers: dict[str, str],
    fake_panel: FakePanel,
    trial_subscriber: str,
    engine: AsyncEngine,
) -> None:
    """Отвязка устройства — ежедневная работа поддержки: человек сменил телефон."""
    user_id = await _subscriber_id(engine)
    fake_panel.add_device(_panel_user_id(fake_panel), "old-phone")

    listed = await api_client.get(f"/api/admin/users/{user_id}/devices", headers=support_headers)
    unlinked = await api_client.delete(
        f"/api/admin/users/{user_id}/devices/old-phone", headers=support_headers
    )
    after = await api_client.get(f"/api/admin/users/{user_id}/devices", headers=support_headers)

    assert listed.json()["used"] == 1
    assert unlinked.status_code == 204
    assert after.json()["used"] == 0


# --- карточка, поиск, журнал ---


async def test_a_silent_panel_does_not_break_the_card(
    api_client: AsyncClient,
    support_headers: dict[str, str],
    fake_panel: FakePanel,
    trial_subscriber: str,
    engine: AsyncEngine,
) -> None:
    """Устройства просит отдельный маршрут именно поэтому: карточка обязана
    открыться и тогда, когда панель молчит."""
    user_id = await _subscriber_id(engine)
    fake_panel.fail_next(3)

    card = await api_client.get(f"/api/admin/users/{user_id}", headers=support_headers)
    devices = await api_client.get(f"/api/admin/users/{user_id}/devices", headers=support_headers)

    assert card.status_code == 200
    assert card.json()["row"]["telegram_id"] == TELEGRAM_SUBSCRIBER_ID
    assert card.json()["row"]["subscription_status"] == "trial"
    assert (devices.status_code, devices.json()["error"]["code"]) == (503, "panel_unavailable")


async def test_card_and_journal_show_the_decision_of_the_staff(
    api_client: AsyncClient, support_headers: dict[str, str], plain_user_id: int
) -> None:
    """Решение персонала — событие ленты: не показать его сразу значит
    заставить сотрудника гадать, прошла ли команда."""
    await api_client.post(f"/api/admin/users/{plain_user_id}/mute", headers=support_headers)

    card = await api_client.get(f"/api/admin/users/{plain_user_id}", headers=support_headers)
    journal = await api_client.get(
        f"/api/admin/users/{plain_user_id}/journal", headers=support_headers
    )

    assert card.status_code == 200
    assert card.json()["row"]["support_muted"] is True
    assert card.json()["row"]["banned"] is False
    assert card.json()["email_verified"] is True
    assert journal.status_code == 200
    assert [entry["kind"] for entry in journal.json()] == ["staff"]
    assert journal.json()[0]["title"] == "Поддержка закрыта"


async def test_unknown_person_is_a_404_everywhere(
    api_client: AsyncClient, support_headers: dict[str, str]
) -> None:
    """Номер из чужой вкладки не должен приводить к 500.

    Сверяется и сообщение: несуществующий маршрут отвечает тем же 404 с тем же
    кодом `not_found`, и без этой проверки набор проходил бы вхолостую — ровно
    так же, как до появления самих маршрутов.
    """
    card = await api_client.get(f"/api/admin/users/{MISSING_USER_ID}", headers=support_headers)
    journal = await api_client.get(
        f"/api/admin/users/{MISSING_USER_ID}/journal", headers=support_headers
    )
    blocked = await api_client.post(
        f"/api/admin/users/{MISSING_USER_ID}/block", headers=support_headers
    )

    assert card.status_code == 404
    assert card.json()["error"]["message"] == "пользователь не найден"
    assert journal.status_code == 404
    assert journal.json()["error"]["message"] == "пользователь не найден"
    assert blocked.status_code == 404
    assert blocked.json()["error"]["message"] == "пользователь не найден"


# --- действия ---


async def test_repeated_block_reports_that_nothing_changed(
    api_client: AsyncClient,
    support_headers: dict[str, str],
    plain_user_id: int,
    engine: AsyncEngine,
) -> None:
    """Интерфейсу нужно отличать «заблокировали» от «уже был заблокирован»."""
    first = await api_client.post(
        f"/api/admin/users/{plain_user_id}/block", headers=support_headers
    )
    second = await api_client.post(
        f"/api/admin/users/{plain_user_id}/block", headers=support_headers
    )
    released = await api_client.post(
        f"/api/admin/users/{plain_user_id}/unblock", headers=support_headers
    )

    assert [first.json(), second.json(), released.json()] == [
        {"changed": True},
        {"changed": False},
        {"changed": True},
    ]
    async with create_session_factory(engine)() as session:
        person = await session.get(User, plain_user_id)
    assert person is not None and person.status is UserStatus.active


async def test_mute_closes_the_conversation_and_unmute_opens_it(
    api_client: AsyncClient, support_headers: dict[str, str], plain_user_id: int
) -> None:
    """Заглушение не трогает ни подписку, ни оплату: закрыт только разговор."""
    muted = await api_client.post(f"/api/admin/users/{plain_user_id}/mute", headers=support_headers)
    repeated = await api_client.post(
        f"/api/admin/users/{plain_user_id}/mute", headers=support_headers
    )
    opened = await api_client.post(
        f"/api/admin/users/{plain_user_id}/unmute", headers=support_headers
    )

    assert [muted.json(), repeated.json(), opened.json()] == [
        {"changed": True},
        {"changed": False},
        {"changed": True},
    ]


async def test_a_colleague_cannot_be_blocked(
    api_client: AsyncClient,
    support_headers: dict[str, str],
    admin_headers: dict[str, str],
    engine: AsyncEngine,
) -> None:
    """Кнопка в админке не должна становиться оружием против своих."""
    async with create_session_factory(engine)() as session:
        colleague = await session.execute(select(User.id).where(User.telegram_id == 900_001))
        colleague_id = int(colleague.scalar_one())

    refused = await api_client.post(
        f"/api/admin/users/{colleague_id}/block", headers=support_headers
    )

    assert refused.json()["error"]["code"] == "staff_immune"
    assert admin_headers


async def test_revoked_link_replaces_the_dead_address(
    api_client: AsyncClient,
    support_headers: dict[str, str],
    fake_panel: FakePanel,
    trial_subscriber: str,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Панель меняет shortUuid, и наш адрес обязан перезаписаться её ответом:
    иначе кабинет продолжит показывать мёртвую ссылку."""
    from repibot_api.routers.admin import users

    user_id = await _subscriber_id(engine)
    monkeypatch.setattr(users, "panel_client", _revoking_panel(fake_panel))

    response = await api_client.post(
        f"/api/admin/users/{user_id}/subscription/revoke-link", headers=support_headers
    )

    assert response.status_code == 200
    assert response.json()["subscription_url"] == f"{BASE_URL}/sub/{NEW_SHORT_UUID}"
    async with create_session_factory(engine)() as session:
        person = await session.get(User, user_id)
    assert person is not None
    assert person.remnawave_short_uuid == NEW_SHORT_UUID
    assert person.remnawave_subscription_url == f"{BASE_URL}/sub/{NEW_SHORT_UUID}"
    assert trial_subscriber != person.remnawave_subscription_url


async def test_a_silent_panel_does_not_pretend_the_link_changed(
    api_client: AsyncClient,
    support_headers: dict[str, str],
    fake_panel: FakePanel,
    trial_subscriber: str,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Пока панель не подтвердила новую ссылку, старая ещё работает: писать
    её в базу изменённой нельзя."""
    from repibot_api.routers.admin import users

    user_id = await _subscriber_id(engine)
    monkeypatch.setattr(users, "panel_client", fake_panel.client)
    fake_panel.fail_next(3)

    response = await api_client.post(
        f"/api/admin/users/{user_id}/subscription/revoke-link", headers=support_headers
    )

    assert (response.status_code, response.json()["error"]["code"]) == (503, "panel_unavailable")
    async with create_session_factory(engine)() as session:
        person = await session.get(User, user_id)
    assert person is not None
    assert person.remnawave_subscription_url == trial_subscriber
