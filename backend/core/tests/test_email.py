"""Письма: шаблоны, выбор языка, доставка через outbox."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.i18n import translate
from repibot_core.integrations.email.sender import (
    EmailMessage,
    LoggingEmailSender,
    build_sender,
)
from repibot_core.integrations.email.templates import (
    render_email_change,
    render_password_reset,
    render_verification,
)
from repibot_core.services.email_dispatch import TOPIC_EMAIL_VERIFY, build_dispatcher
from repibot_core.settings import Settings


def test_verification_letter_contains_link_in_both_parts() -> None:
    link = "https://example.org/verify-email?token=abc"

    message = render_verification("ru", link=link, to="user@example.org")

    assert link in message.text
    assert link in message.html
    assert message.to == "user@example.org"


def test_letters_differ_by_language() -> None:
    ru = render_verification("ru", link="https://example.org/x", to="a@example.org")
    en = render_verification("en", link="https://example.org/x", to="a@example.org")

    assert ru.subject != en.subject


def test_unknown_language_falls_back_to_russian() -> None:
    assert translate("de", "email.verify.subject") == translate("ru", "email.verify.subject")


def test_reset_and_change_letters_are_distinct() -> None:
    reset = render_password_reset("ru", link="https://example.org/r", to="a@example.org")
    change = render_email_change("ru", link="https://example.org/c", to="b@example.org")

    assert reset.subject != change.subject


async def test_logging_sender_keeps_messages() -> None:
    sender = LoggingEmailSender()

    await sender.send(EmailMessage(to="a@example.org", subject="s", text="t", html="<p>t</p>"))

    assert len(sender.sent) == 1


def test_build_sender_respects_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_SENDER", "log")
    settings = Settings()  # type: ignore[call-arg]

    assert isinstance(build_sender(settings), LoggingEmailSender)


def test_letters_never_contain_raw_token_in_logs() -> None:
    """Ссылка в письме содержит токен; в журнал попадает только адрес.

    Журнал доступен шире, чем почтовый ящик: токен из него позволил бы
    подтвердить чужую почту.
    """
    sender = LoggingEmailSender()

    assert "token" not in sender.describe(
        EmailMessage(to="a@example.org", subject="s", text="https://x/?token=secret", html="")
    )


@pytest.mark.docker
async def test_queued_letter_is_delivered(db_session: AsyncSession) -> None:
    sender = LoggingEmailSender()
    await OutboxRepository(db_session).add(
        TOPIC_EMAIL_VERIFY,
        {"language": "ru", "to": "user@example.org", "link": "https://example.org/v?token=x"},
    )
    await db_session.commit()

    delivered = await build_dispatcher(sender).process(db_session)

    assert delivered == 1
    assert sender.sent[0].to == "user@example.org"
