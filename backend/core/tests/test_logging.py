"""Логи читает машина, а секреты в них не попадают никогда."""

import json
import logging
from io import StringIO

from repibot_core.logging import JsonFormatter, SecretFilter, request_id_var, set_request_id


def _capture(logger_name: str) -> tuple[logging.Logger, StringIO]:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretFilter())
    logger = logging.getLogger(logger_name)
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger, stream


def test_record_is_valid_json_with_expected_fields() -> None:
    logger, stream = _capture("test.json")

    logger.info("подписка продлена")

    payload = json.loads(stream.getvalue())
    assert payload["message"] == "подписка продлена"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.json"
    assert "timestamp" in payload


def test_request_id_is_attached_when_set() -> None:
    logger, stream = _capture("test.request")
    set_request_id("req-42")

    logger.info("готово")

    assert json.loads(stream.getvalue())["request_id"] == "req-42"
    request_id_var.set(None)


def test_bot_token_is_masked() -> None:
    logger, stream = _capture("test.secret")

    logger.info("вызов https://api.telegram.org/bot123456:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw/getMe")

    output = stream.getvalue()
    assert "AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw" not in output
    assert "***" in output


def test_authorization_header_value_is_masked() -> None:
    logger, stream = _capture("test.header")

    logger.info("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature")

    output = stream.getvalue()
    assert "eyJhbGciOiJIUzI1NiJ9.payload.signature" not in output
    assert "***" in output


def test_exception_info_is_included() -> None:
    logger, stream = _capture("test.exc")

    try:
        raise ValueError("панель недоступна")
    except ValueError:
        logger.exception("сбой синхронизации")

    payload = json.loads(stream.getvalue())
    assert "ValueError" in payload["exception"]
    assert "панель недоступна" in payload["exception"]
