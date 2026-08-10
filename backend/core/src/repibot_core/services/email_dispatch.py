"""Обработчики почтовых тем очереди.

Полезная нагрузка сообщения содержит только язык, адрес и ссылку. Ни токена
отдельно, ни идентификатора пользователя: обработчик не должен уметь ничего
кроме отправки того, что ему передали.
"""

from __future__ import annotations

from typing import Any

from repibot_core.integrations.email.sender import EmailSender, build_sender
from repibot_core.integrations.email.templates import (
    render_email_change,
    render_password_reset,
    render_payment_notification,
    render_verification,
)
from repibot_core.services.outbox import OutboxDispatcher
from repibot_core.services.payment_notifications import TOPIC_PAYMENT_EMAIL
from repibot_core.settings import get_settings

TOPIC_EMAIL_VERIFY = "email.verify"
# Имя темы очереди, а не пароль: ruff судит по слову «password» в имени.
TOPIC_PASSWORD_RESET = "email.password_reset"  # noqa: S105
TOPIC_EMAIL_CHANGE = "email.change"

_RENDERERS = {
    TOPIC_EMAIL_VERIFY: render_verification,
    TOPIC_PASSWORD_RESET: render_password_reset,
    TOPIC_EMAIL_CHANGE: render_email_change,
}


def build_dispatcher(sender: EmailSender | None = None) -> OutboxDispatcher:
    """Собирает диспетчер с почтовыми темами.

    Отправитель принимается параметром, чтобы тест подставил свой без правки
    настроек окружения.
    """
    resolved = sender if sender is not None else build_sender(get_settings())
    dispatcher = OutboxDispatcher()

    for topic, renderer in _RENDERERS.items():

        async def handle(payload: dict[str, Any], renderer=renderer) -> None:  # type: ignore[no-untyped-def]
            message = renderer(payload["language"], link=payload["link"], to=payload["to"])
            await resolved.send(message)

        dispatcher.register(topic, handle)

    async def handle_payment(payload: dict[str, Any]) -> None:
        message = render_payment_notification(
            payload["language"],
            # Письмо открывают в браузере, а страница Mini App вне Telegram
            # войти не может: ведём в кабинет на сайте.
            link=f"{get_settings().public_web_url.rstrip('/')}/account/payments",
            to=payload["recipient"],
            kind=payload["kind"],
            plan=payload["plan"],
        )
        await resolved.send(message)

    dispatcher.register(TOPIC_PAYMENT_EMAIL, handle_payment)

    return dispatcher
