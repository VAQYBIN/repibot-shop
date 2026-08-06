"""Параметры проверяющей стороны и чтение ответа аутентификатора.

Чистые преобразования без ввода-вывода: адрес сайта → RP ID и origin, тело
запроса → challenge и идентификатор ключа. Криптографию считает библиотека
webauthn, здесь только то, что нужно до её вызова.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from webauthn.helpers import base64url_to_bytes

# Имя видно человеку в системном окне выбора ключа.
RP_NAME = "Re:Pibot"

# Браузер не пишет стандартный порт в origin, а сравнение origin у библиотеки
# посимвольное: с ":443" в адресе сайта не сошёлся бы ни один ответ.
DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass(frozen=True, slots=True)
class RelyingParty:
    rp_id: str
    origin: str


def relying_party(public_web_url: str) -> RelyingParty:
    """Выводит RP ID и origin из адреса сайта.

    Отдельной переменной окружения у них нет намеренно: разойтись эти значения
    не должны, а ключ, зарегистрированный на один RP ID, на другом не работает
    вовсе — рассинхронизация превратилась бы в потерю всех passkey сразу.

    Origin собирается из частей, а не берётся как `netloc`: браузер шлёт имя
    домена в нижнем регистре, без учётных данных и без стандартного порта.
    """
    parts = urlsplit(public_web_url)
    try:
        port = parts.port
    except ValueError as error:
        msg = f"PUBLIC_WEB_URL не похож на адрес: {public_web_url}"
        raise ValueError(msg) from error
    if not parts.hostname or not parts.scheme:
        msg = f"PUBLIC_WEB_URL не похож на адрес: {public_web_url}"
        raise ValueError(msg)
    scheme = parts.scheme.lower()
    suffix = "" if port is None or port == DEFAULT_PORTS.get(scheme) else f":{port}"
    return RelyingParty(rp_id=parts.hostname, origin=f"{scheme}://{parts.hostname}{suffix}")


def challenge_from_response(credential: dict[str, Any]) -> bytes:
    """Достаёт challenge из clientDataJSON.

    Так серверу не нужно ни состояние в сессии, ни лишнее поле в запросе:
    challenge пришёл обратно внутри подписанных данных, и по нему же ищется
    запись в Valkey.
    """
    try:
        raw = credential["response"]["clientDataJSON"]
        client_data = json.loads(base64url_to_bytes(raw))
        return base64url_to_bytes(client_data["challenge"])
    except (KeyError, TypeError, ValueError) as error:
        msg = "ответ аутентификатора не разбирается"
        raise ValueError(msg) from error


def credential_id_from_response(credential: dict[str, Any]) -> bytes:
    try:
        return base64url_to_bytes(credential["rawId"])
    except (KeyError, TypeError, ValueError) as error:
        msg = "ответ аутентификатора без идентификатора ключа"
        raise ValueError(msg) from error
