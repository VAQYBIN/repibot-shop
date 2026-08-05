"""Разрешённые источники запросов.

Отдельный модуль, а не часть `main`: список нужен и роутеру обновления сессии,
а он импортируется самим `main` — держать функцию там значило бы замкнуть цикл
импортов.
"""

from __future__ import annotations

from urllib.parse import urlsplit


def allowed_origins(*urls: str) -> list[str]:
    """Приводит адреса к origin и убирает повторы, сохраняя порядок.

    В настройках хранятся адреса страниц (`PUBLIC_APP_URL` — с путём `/app`),
    а браузер присылает в Origin только схему, хост и порт. Запись с путём
    не совпадёт ни с одним запросом.
    """
    origins: list[str] = []
    for url in urls:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in origins:
            origins.append(origin)
    return origins
