"""Шаблоны писем.

HTML-часть собирается из одного каркаса: письма различаются текстом, а не
вёрсткой. Цвета — из бренд-бука, значениями, потому что CSS-переменные в
почтовых клиентах не работают.
"""

from __future__ import annotations

from jinja2 import Environment

from repibot_core.i18n import translate
from repibot_core.integrations.email.sender import EmailMessage

INK = "#1A1A18"
PAPER = "#FAF9F7"
JADE = "#17A67C"
# Ссылка — мелкий текст, а контраст Jade к светлому фону 3.1:1. Бренд-бук для
# такого случая требует Jade Deep: письмо должно читаться и на плохом экране.
JADE_DEEP = "#0E6B50"

_LAYOUT = Environment(autoescape=True).from_string(
    """<!doctype html>
<html lang="{{ language }}">
  <body style="margin:0;padding:24px;background:{{ paper }};color:{{ ink }};
               font-family:-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.5">
    <div style="max-width:520px;margin:0 auto">
      <p style="font-size:20px;font-weight:600;margin:0 0 24px">
        Re<span style="color:{{ jade }}">:</span>Pibot
      </p>
      {% for paragraph in paragraphs %}
        <p style="margin:0 0 16px">{{ paragraph }}</p>
      {% endfor %}
      <p style="margin:24px 0 0">
        <a href="{{ link }}" style="color:{{ jade_deep }}">{{ link }}</a>
      </p>
    </div>
  </body>
</html>
"""
)


def _render(language: str, *, to: str, subject_key: str, body_key: str, link: str) -> EmailMessage:
    text = translate(language, body_key, link=link)
    paragraphs = [line for line in text.split("\n") if line.strip() and link not in line]
    html = _LAYOUT.render(
        language=language,
        paragraphs=paragraphs,
        link=link,
        ink=INK,
        paper=PAPER,
        jade=JADE,
        jade_deep=JADE_DEEP,
    )
    return EmailMessage(to=to, subject=translate(language, subject_key), text=text, html=html)


def render_verification(language: str, *, link: str, to: str) -> EmailMessage:
    return _render(
        language,
        to=to,
        subject_key="email.verify.subject",
        body_key="email.verify.body",
        link=link,
    )


def render_password_reset(language: str, *, link: str, to: str) -> EmailMessage:
    return _render(
        language,
        to=to,
        subject_key="email.password_reset.subject",
        body_key="email.password_reset.body",
        link=link,
    )


def render_email_change(language: str, *, link: str, to: str) -> EmailMessage:
    return _render(
        language,
        to=to,
        subject_key="email.change.subject",
        body_key="email.change.body",
        link=link,
    )


def render_notification(
    language: str, *, link: str, to: str, subject: str, body: str
) -> EmailMessage:
    """Письмо уведомления в общем каркасе бренда.

    Тема и тело приходят готовыми: вид события знает свои ключи перевода, а
    вёрстка — нет. Каркас при этом общий с остальными письмами: разведённая по
    двум файлам, она расходится на первой же правке шапки.
    """
    html = _LAYOUT.render(
        language=language,
        paragraphs=[body],
        link=link,
        ink=INK,
        paper=PAPER,
        jade=JADE,
        jade_deep=JADE_DEEP,
    )
    return EmailMessage(to=to, subject=subject, text=body, html=html)
