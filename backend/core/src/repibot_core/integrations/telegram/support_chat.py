"""Супергруппа поддержки: топик на обращение.

Три вызова Bot API и ничего больше. Отдельно от `BotApi` потому, что тот
говорит с личными чатами пользователей, а здесь — рабочее место персонала:
у них разные адресаты и разная цена ошибки.
"""

from __future__ import annotations

from typing import Any

import httpx

from repibot_core.settings import Settings

TIMEOUT_SECONDS = 10.0


class SupportChat:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)

    async def create_topic(self, name: str) -> int:
        """Заводит тему и возвращает её идентификатор."""
        result = await self._call("createForumTopic", {"chat_id": self._chat_id(), "name": name})
        return int(result["message_thread_id"])

    async def post(self, topic_id: int, text: str) -> int:
        """Кладёт сообщение в тему и возвращает его номер.

        Без `parse_mode`: чужой текст в топике не должен превращаться в
        разметку и подделывать служебное сообщение, а обычная звёздочка в
        обращении иначе роняла бы отправку разбором разметки.
        """
        result = await self._call(
            "sendMessage",
            {"chat_id": self._chat_id(), "message_thread_id": topic_id, "text": text},
        )
        return int(result["message_id"])

    async def close_topic(self, topic_id: int) -> None:
        await self._call(
            "closeForumTopic", {"chat_id": self._chat_id(), "message_thread_id": topic_id}
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _chat_id(self) -> int:
        chat_id = self._settings.support_chat_id
        if chat_id is None:
            # Собирать клиент без супергруппы незачем: тем `support.outbound`
            # при пустой настройке в очереди просто не появляется.
            msg = "SUPPORT_CHAT_ID не задан"
            raise RuntimeError(msg)
        return chat_id

    async def _call(self, method: str, body: dict[str, Any]) -> dict[str, Any]:
        """Один вызов Bot API. Отказ — исключение, а не тихий None.

        Проглоченный отказ пометил бы сообщение очереди доставленным, и
        обращение исчезло бы, не дойдя ни до кого. Исключение разбор очереди
        превратит в отложенную попытку.
        """
        token = self._settings.bot_token.get_secret_value()
        # Токен в пути — требование Bot API. В журнал этот адрес не пишется.
        response = await self._client.post(
            f"https://api.telegram.org/bot{token}/{method}", json=body
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("ok") is not True:
            msg = f"Bot API отверг {method}: {payload.get('description')}"
            raise RuntimeError(msg)
        result = payload.get("result")
        return result if isinstance(result, dict) else {}
