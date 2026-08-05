"""Тексты, которые формирует бэкенд: письма и сообщения бота.

Ошибки API здесь не переводятся — они уходят кодом, фразу подбирает фронтенд.
Письмо и сообщение бота переводить больше некому.
"""

from __future__ import annotations

from typing import Any

FALLBACK = "ru"

_MESSAGES: dict[str, dict[str, str]] = {
    "ru": {
        "email.verify.subject": "Подтвердите почту в Re:Pibot",
        "email.verify.body": (
            "Здравствуйте!\n\nЧтобы завершить регистрацию, откройте ссылку:\n{link}\n\n"
            "Ссылка действует сутки. Если вы не регистрировались, письмо можно удалить."
        ),
        "email.password_reset.subject": "Сброс пароля в Re:Pibot",
        "email.password_reset.body": (
            "Чтобы задать новый пароль, откройте ссылку:\n{link}\n\n"
            "Ссылка действует час. Если вы не запрашивали сброс, ничего делать не нужно."
        ),
        "email.change.subject": "Подтвердите новый адрес почты",
        "email.change.body": (
            "Вы указали этот адрес как новый в Re:Pibot. Чтобы подтвердить, откройте ссылку:\n"
            "{link}\n\nСсылка действует час."
        ),
        "bot.start.greeting": "Здравствуйте, {name}. Это Re:Pibot.",
        "bot.start.open_app": "Открыть приложение",
        "bot.language.choose": "Выберите язык",
        "bot.language.saved": "Язык сохранён",
    },
    "en": {
        "email.verify.subject": "Confirm your email for Re:Pibot",
        "email.verify.body": (
            "Hello!\n\nTo finish signing up, open this link:\n{link}\n\n"
            "The link is valid for 24 hours. If you did not sign up, ignore this message."
        ),
        "email.password_reset.subject": "Reset your Re:Pibot password",
        "email.password_reset.body": (
            "To set a new password, open this link:\n{link}\n\n"
            "The link is valid for one hour. If you did not ask for it, no action is needed."
        ),
        "email.change.subject": "Confirm your new email address",
        "email.change.body": (
            "You set this address as your new one in Re:Pibot. To confirm, open this link:\n"
            "{link}\n\nThe link is valid for one hour."
        ),
        "bot.start.greeting": "Hello, {name}. This is Re:Pibot.",
        "bot.start.open_app": "Open the app",
        "bot.language.choose": "Choose a language",
        "bot.language.saved": "Language saved",
    },
}


def translate(language: str, key: str, **params: Any) -> str:
    """Берёт строку для языка, при незнакомом языке — русскую."""
    messages = _MESSAGES.get(language, _MESSAGES[FALLBACK])
    template = messages.get(key) or _MESSAGES[FALLBACK][key]
    return template.format(**params) if params else template
