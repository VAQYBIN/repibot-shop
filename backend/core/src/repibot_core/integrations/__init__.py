"""Обёртки над внешними системами: панель Remnawave, платежи, почта.

Слой отвечает только за транспорт и типы. Решения о том, что делать
с ответом, принимаются в services.
"""

from repibot_core.integrations.yookassa.client import YooKassaClient, create_yookassa_client

__all__ = ["YooKassaClient", "create_yookassa_client"]
