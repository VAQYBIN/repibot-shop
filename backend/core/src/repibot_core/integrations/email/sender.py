"""Отправка писем: интерфейс и две реализации."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from email.message import EmailMessage as MimeMessage
from typing import Protocol

import aiosmtplib

from repibot_core.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


def _describe(message: EmailMessage) -> str:
    """Строка для журнала: адрес и тема, без тела.

    В теле лежит ссылка с токеном подтверждения, а журнал доступен шире, чем
    почтовый ящик получателя.
    """
    return f"письмо «{message.subject}» на {message.to}"


@dataclass
class LoggingEmailSender:
    """Пишет в журнал вместо отправки. Локальная разработка и тесты."""

    sent: list[EmailMessage] = field(default_factory=list)

    def describe(self, message: EmailMessage) -> str:
        return _describe(message)

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)
        # Ссылка нужна разработчику целиком: без неё локально не подтвердить
        # почту. Уровень DEBUG, и в production этот отправитель не используется.
        logger.info("%s (не отправлено, EMAIL_SENDER=log)", _describe(message))
        logger.debug("тело письма: %s", message.text)


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self._settings.smtp_from
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        mime.add_alternative(message.html, subtype="html")

        await aiosmtplib.send(
            mime,
            hostname=self._settings.smtp_host,
            port=self._settings.smtp_port,
            username=self._settings.smtp_username or None,
            password=self._settings.smtp_password.get_secret_value() or None,
            start_tls=self._settings.smtp_starttls,
            timeout=20,
        )
        logger.info("%s отправлено", _describe(message))


def build_sender(settings: Settings) -> EmailSender:
    if settings.email_sender == "smtp":
        return SmtpEmailSender(settings)
    return LoggingEmailSender()
