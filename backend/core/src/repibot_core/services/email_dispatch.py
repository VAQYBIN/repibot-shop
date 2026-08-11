"""Обработчики почтовых тем очереди.

Полезная нагрузка сообщения содержит язык, адрес и то, чем различаются письма
одного вида. Токена в ней нет отдельно от готовой ссылки: обработчик не должен
уметь ничего кроме отправки того, что ему передали.
"""

from __future__ import annotations

from typing import Any

from repibot_core.i18n import translate
from repibot_core.integrations.email.sender import EmailSender, build_sender
from repibot_core.integrations.email.templates import (
    render_email_change,
    render_notification,
    render_password_reset,
    render_verification,
)
from repibot_core.services.notifications import PAYLOAD_KEYS, TOPIC_NOTIFY_EMAIL, resolve_kind
from repibot_core.services.outbox import OutboxDispatcher
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

    async def handle_notify(payload: dict[str, Any]) -> None:
        language = str(payload["language"])
        kind = resolve_kind(str(payload["kind"]))
        # Служебные поля не попадают в текст: translate подставляет всё, что
        # получил, и лишний ключ в шаблоне даёт KeyError на живом уведомлении.
        params = {key: value for key, value in payload.items() if key not in PAYLOAD_KEYS}
        message = render_notification(
            language,
            to=str(payload["recipient"]),
            subject=translate(language, f"{kind.text_key}.subject", **params),
            body=translate(language, f"{kind.text_key}.body", **params),
            # Адрес берётся у вида события: одна ссылка на все письма привела
            # бы человека с ответом поддержки на страницу оплат.
            link=f"{get_settings().public_web_url.rstrip('/')}{kind.link_path}",
        )
        await resolved.send(message)

    dispatcher.register(TOPIC_NOTIFY_EMAIL, handle_notify)

    return dispatcher
