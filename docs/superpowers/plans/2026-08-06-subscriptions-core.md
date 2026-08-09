# Подписки, этап 2a — план реализации

> **Для агентов:** ОБЯЗАТЕЛЬНЫЙ ПОДСКИЛЛ: используйте superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans для выполнения плана задача за задачей. Шаги размечены чекбоксами (`- [ ]`).

**Цель:** дать системе тарифы, подписку и связь с панелью Remnawave 3.2.1 — так, чтобы админ завёл тариф через API, пользователь активировал триал и получил рабочую ссылку подписки.

**Архитектура:** дату окончания считаем только мы, панель к ней приводится одной идемпотентной функцией `ProvisioningService.reconcile`. У неё три вызывающих: сервис подписки сразу после коммита, разбор `outbox` при неудаче и крон-реконсиляция. Начисление дней вынесено в `SubscriptionService.grant_days` — в подпроекте 3 её позовёт финализация платежа, и больше ничего менять не придётся.

**Стек:** Python 3.13, SQLAlchemy 2.0, Alembic, FastAPI, httpx, tenacity, TaskIQ, Valkey, Postgres 18; pytest, testcontainers, fakeredis.

**Спецификация:** [docs/superpowers/specs/2026-08-06-subscriptions-design.md](../specs/2026-08-06-subscriptions-design.md)

**Предшествующий подпроект:** [1b — passkey и Telegram](./2026-08-06-identity-passkeys-telegram.md), выполнен полностью.

**Следующий этап:** 2b — устройства, трафик, вебхуки панели, реконсиляция и интерфейсы веба и MiniApp. Пишется после того, как этот выполнен.

## Состояние на старте

`uv run check` на ветке `dev` был **красным**: схема панели обновлена до 3.2.1, а генератор моделей искал корневую схему `GetUserByUuidResponseDto`, которой в 3.2.1 нет. Задача 1 починила это первой.

## Состояние выполнения

Этап выполнен полностью, задачи 1–16.

**Проверка на живой панели Remnawave 3.2.1 пройдена 2026-08-06** владельцем
развёртывания, целиком по сценарию задачи 16: сквады читаются из панели, тариф
из них создаётся, триал активируется, ссылка подписки открывается и клиент по
ней подключается, пользователь в панели заведён с ожидаемыми именем, тегом,
датой и составом сквадов. Сценарий с недоступной панелью тоже подтверждён:
начисление при мёртвой панели оставляет подписку в `pending_provision`, а после
её подъёма воркер доводит выдачу доступа.

Расхождений между заглушкой и живой панелью не нашлось — предположения о
поведении 3.2.1, на которых построен этап, оказались верны.

Задачи шли волнами: внутри волны — параллельные исполнители, между волнами — полный прогон `uv run check` и коммиты.

| Волна | Задачи | Состояние |
|---|---|---|
| 1 | 1 модели панели, 2 домен, 4 настройки | готово |
| 2 | 3 таблицы, 6 фасады панели | готово |
| 3 | 5 репозитории, 7 заглушка панели | готово |
| — | `services/errors.py` вынесен ведущим до волны 4 | готово |
| 4 | 8 сервис тарифов, 9 примирение | готово |
| 5 | 10 админское API тарифов, 11 сервис подписок | готово |
| 6 | 12 клиентское API, 13 крон истечения | готово |
| 7 | 14 админское начисление | готово |
| 8 | 15 типы фронтенда, 16 документация и проверка на живой панели | готово |

Волны пересобраны против исходной разбивки дважды: модель подписки импортирует
`SubscriptionState` из домена и не может идти с ним в одной волне, а задачи 12 и
14 делят `schemas.py`. Общий `services/errors.py` ведущий написал сам до запуска
волны 4 — иначе два исполнителя создавали бы один файл.

### Что нашлось при сборке

Помимо задач плана в этап вошли правки, найденные по ходу. Листинги в задачах
местами разошлись с итоговым кодом; источник истины — код.

**Панель и генератор моделей**

- **`--use-annotated` использовать нельзя.** Флаг напрашивается, чтобы вылечить
  слепоту mypy к позиционному `Field(None, ...)`, но он переносит в `Annotated`
  ограничения схемы, и `pattern` из описания даты применяется к полю типа
  `AwareDatetime` как строковый. Разбор любого ответа панели падает на
  `expireAt`. Вместо флага подключён плагин `pydantic.mypy`; шесть ставших
  ненужными `# type: ignore` убраны.
- **`PATCH /api/users` шлёт только явно заданные поля** (`exclude_unset`).
  У `trafficLimitStrategy` в схеме значение по умолчанию `NO_RESET`, а не
  `null`, и отбор по `None` его не отсекал: правка одного лимита устройств
  молча сбрасывала пользователю стратегию сброса трафика.
- **Числовой идентификатор приходит как `42.0`** — в схеме 3.2.1 это `number`.
  Везде, где читается `id` панели, стоит приведение через `int(...)`.
- **`activeInternalSquads` расходится между запросом и ответом**: в запросе
  список uuid, в ответе объекты `{uuid, name}`. Заглушка преобразует их и при
  создании, и при обновлении.
- Дефолты enum-полей генератор пишет сырыми строками, поэтому pydantic шумит
  `PydanticSerializationUnexpectedValue`, если поле не задать явно. Наш код
  задаёт их всегда.

**Данные**

- **Ссылка подписки хранится в `users.remnawave_subscription_url`**, а не
  собирается из `REMNAWAVE_BASE_URL`: публичный домен страницы подписки
  настраивается в панели отдельно, а `revoke` меняет `shortUuid`.
- Модели обязаны объявлять те же индексы, что создаёт миграция, иначе
  автогенерация Alembic видит дрейф и `test_migrations_match_the_models` краснеет.
- `test_migrations.py` проверял наличие `remnawave_uuid` — поправлен вместе с
  заменой колонки.

**Поведение**

- **Статус подписки переводится в рабочий до обращения к панели.** Примирение
  при `pending_provision` шлёт панели `status: DISABLED`, поэтому по
  буквальному коду плана первая выдача создавала бы пользователя панели
  заблокированным, а доступ открывался бы только следующим разбором очереди.
  При отказе панели статус возвращается в `pending_provision`.
- **Смена тарифа с сохранением остатка начисляет остаток**, а не срок нового
  тарифа поверх него: листинг в задаче 11 противоречил собственному тесту и
  давал двойной счёт.
- **Даты сравниваются до секунды.** Тест идемпотентности этого не ловил:
  заглушка возвращала отправленную дату без потерь, и округление оказывалось
  пустой операцией. Добавлен тест, округляющий дату в заглушке до миллисекунд —
  как это делает настоящая панель.
- **Клиенты httpx закрываются.** Крон разбора очереди идёт раз в минуту, крон
  истечения — раз в час, роутеры собирают клиент на запрос; брошенный
  `AsyncClient` тёк бы сокетами всё время работы процесса.
- `AuditRepository` называет метод `record`, а не `add`.

**Тесты**

- Два теста в листингах были ложно-зелёными: проверка единственности подписки
  падала на `NOT NULL` раньше уникального индекса, а проверка единственного
  триального тарифа роняла `IntegrityError` до `pytest.raises`.
- Тест «триал раз на Telegram» в листинге неисполним: `users.telegram_id`
  уникален, и два живых пользователя с одним идентификатором не создаются.
  Переписан на настоящий сценарий накрутки — удаление аккаунта и повторная
  регистрация.
- `user_headers` — пользователь без Telegram, поэтому `trial_available` для
  него `false`; проверка новичка разделена на две.
- Тесты, где выдача доступа происходит на самом деле, требуют заглушку панели:
  без неё запрос уходит в сеть, и подписка остаётся в `pending_provision`.

## Волны выполнения

Внутри волны задачи идут параллельными исполнителями, между волнами — полный прогон `uv run check` и коммиты.

| Волна | Задачи | Почему вместе |
|---|---|---|
| 1 | 1 модели панели, 2 домен подписок, 4 настройки | Ни одного общего файла и ни одной общей зависимости |
| 2 | 3 таблицы, 6 фасады панели | 3 после 2 — модель подписки импортирует `SubscriptionState`; 6 после 1 и 4 |
| 3 | 5 репозитории, 7 заглушка панели | 5 после 3, 7 после 6 |
| 4 | 8 сервис тарифов, 9 примирение | 8 после 5 и 6, 9 после 5, 6 и 7 |
| 5 | 10 админское API тарифов, 11 сервис подписок | 10 после 8, 11 после 2, 5 и 9 |
| 6 | 12 клиентское API, 13 крон истечения, 14 админское начисление | Все после 11, файлы разные |
| 7 | 15 типы фронтенда, 16 документация и ручная проверка | После всех эндпоинтов |

## Глобальные ограничения

- Ветка работы — `dev`. Отдельные ветки, если понадобятся, создаются от `dev`.
- Каждая задача заканчивается прогоном `uv run check` без ошибок и одним коммитом. Сообщение коммита на русском в формате `тип: краткое описание`.
- Тест пишется первым и падает до реализации.
- Бизнес-логика — только в `backend/core/src/repibot_core/services` и `.../domain`. В роутерах FastAPI и хендлерах aiogram её нет.
- Комментарии, докстринги и сообщения — на русском. Комментарий объясняет причину решения, а не пересказывает код.
- `mypy` в strict и `ruff` с набором из `pyproject.toml` — блокирующие. Аннотации обязательны везде, включая тесты.
- Новая переменная окружения добавляется одновременно в `Settings`, `.env.example` и `docs/deployment.md`.
- Тексты ошибок API не локализуются: ответ несёт код, фразу подбирает фронтенд. Коды этапа: `panel_unavailable`, `trial_already_used`, `trial_requires_telegram`, `trial_disabled`, `subscription_exists`, `plan_not_found`, `plan_inactive`, `plan_code_taken`, `plan_squads_unknown`, `subscription_missing`.
- Тесты, которым нужен Postgres, помечаются `pytestmark = pytest.mark.docker`.
- Новых зависимостей этап не требует: `httpx`, `tenacity`, `sqlalchemy`, `alembic`, `taskiq` уже стоят. Ставить или обновлять пакеты в задачах не нужно — `uv.lock` и `pnpm-lock.yaml` общие, и параллельные исполнители за них дерутся.
- `backend/core/src/repibot_core/integrations/remnawave/models.py` — генерируемый файл. Руками не правится никогда; меняется только `tools/gen_remnawave_models.py`, после чего файл перегенерируется.
- Направление зависимостей: `domain` ничего не импортирует из `db`, `integrations` и `services`. Обратное разрешено.

## Проверенные факты о панели 3.2.1

Значения получены из схемы `docs/remnawave-api/api-1.json` и пробным запуском генератора 2026-08-06, а не из документации.

| Факт | Значение |
|---|---|
| Идентификатор пользователя | Число (`"type": "number"`), не UUID. Поля `uuid` в объекте пользователя нет |
| Поиск пользователя | `POST /api/users/resolve`, тело `{"id"\|"shortUuid"\|"username"}` |
| Обновление | `PATCH /api/users`, идентификатор в теле полем `id` |
| Создание | `POST /api/users`, обязательны `username` и `expireAt` |
| Ограничение `username` | 3–36 символов, `^[a-zA-Z0-9_-]+$` |
| Ограничение `tag` | до 16 символов, `^[A-Z0-9_]+$` |
| Сквады | `GET /api/internal-squads`, ответ `response.internalSquads[]` с `uuid` и `name` |
| Версия OpenAPI | 3.0.0, поля помечены `nullable: true` |

**Ловушка генератора.** `datamodel-code-generator` по умолчанию игнорирует `nullable: true` у обязательных полей: `telegramId`, `email`, `description`, `tag`, `hwidDeviceLimit`, `externalSquadUuid`, `subRevokedAt` и `lastTrafficResetAt` получаются необязательными к `None`, и первый же пользователь панели без тега валит разбор ответа. Лечится флагом `--strict-nullable`, который добавляется в задаче 1.

---

### Задача 1: Модели панели 3.2.1

**Файлы:**
- Изменить: `tools/gen_remnawave_models.py`
- Изменить (перегенерацией): `backend/core/src/repibot_core/integrations/remnawave/models.py`
- Создать: `backend/core/src/repibot_core/integrations/remnawave/types.py`
- Тест: `backend/core/tests/test_remnawave_types.py`

**Интерфейсы:**
- Отдаёт: `PanelUser`, `PanelSquad`, `PanelStatus`, `PanelTrafficStrategy` из `repibot_core.integrations.remnawave.types` — все последующие задачи берут типы панели только оттуда, а не из `models.py`.

Генератор даёт вложенным безымянным объектам номерные имена (`Response`, `Response1`, `Status1`, `Status2`). Ссылаться на них из кода нельзя: добавление корневой схемы сдвигает нумерацию. Псевдонимы в `types.py` и тест на состав полей ловят такой сдвиг сразу.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_remnawave_types.py
"""Псевдонимы типов панели переживают перегенерацию моделей."""

from __future__ import annotations

from repibot_core.integrations.remnawave.types import PanelSquad, PanelUser


def test_panel_user_has_identity_fields() -> None:
    """Сдвиг нумерации сгенерированных классов не должен пройти молча."""
    assert {"id", "shortUuid", "username", "expireAt", "subscriptionUrl"} <= set(
        PanelUser.model_fields
    )


def test_nullable_fields_allow_none() -> None:
    """Панель присылает null в этих полях; обязательными они быть не могут."""
    for name in ("telegramId", "email", "tag", "hwidDeviceLimit"):
        assert type(None) in PanelUser.model_fields[name].annotation.__args__


def test_panel_squad_has_uuid_and_name() -> None:
    assert {"uuid", "name"} <= set(PanelSquad.model_fields)
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_remnawave_types.py -q`
Ожидание: FAIL, `ModuleNotFoundError: repibot_core.integrations.remnawave.types`

- [ ] **Шаг 3: Расширить генератор**

В `tools/gen_remnawave_models.py` заменить список корневых схем и добавить флаг:

```python
ROOT_SCHEMAS: tuple[str, ...] = (
    "CreateUserBodyDto",
    "GetInternalSquadsResponseDto",
    "ResolveUserBodyDto",
    "UpdateUserBodyDto",
    "UserResponseDto",
)
```

В список аргументов `datamodel_code_generator` добавить `"--strict-nullable"` сразу после `"--use-union-operator"`. Без него поля с `nullable: true` генерируются обязательными, и разбор ответа падает на первом же пользователе без тега.

Заодно поправить докстринг модуля: «Схема панели — 146 эндпоинтов» вместо 142.

- [ ] **Шаг 4: Перегенерировать модели**

Запуск: `uv run python tools/gen_remnawave_models.py`
Ожидание: файл `models.py` перезаписан, около 219 строк, в нём классы `CreateUserBodyDto`, `UpdateUserBodyDto`, `ResolveUserBodyDto`, `GetInternalSquadsResponseDto`, `UserResponseDto`, `InternalSquad`, `ActiveInternalSquad`, `UserTraffic` и номерные `Response`, `Response1`, `Status`, `Status1`, `Status2`.

- [ ] **Шаг 5: Написать псевдонимы**

```python
# backend/core/src/repibot_core/integrations/remnawave/types.py
"""Устойчивые имена для сгенерированных моделей панели.

Генератор называет вложенные безымянные объекты по порядку — Response,
Response1, Status2. Порядок меняется от состава корневых схем, поэтому код
ссылается на псевдонимы отсюда, а не на номерные классы напрямую. Тест
test_remnawave_types проверяет, что псевдоним всё ещё указывает на нужный тип.
"""

from __future__ import annotations

from repibot_core.integrations.remnawave import models

PanelUser = models.Response1
PanelSquad = models.InternalSquad
PanelStatus = models.Status2
PanelTrafficStrategy = models.TrafficLimitStrategy

CreateUserBody = models.CreateUserBodyDto
UpdateUserBody = models.UpdateUserBodyDto
ResolveUserBody = models.ResolveUserBodyDto

__all__ = [
    "CreateUserBody",
    "PanelSquad",
    "PanelStatus",
    "PanelTrafficStrategy",
    "PanelUser",
    "ResolveUserBody",
    "UpdateUserBody",
]
```

- [ ] **Шаг 6: Запустить тесты и проверку генерации**

Запуск: `uv run pytest backend/core/tests/test_remnawave_types.py -q && uv run verify-generated`
Ожидание: PASS и «Сгенерированные файлы актуальны».

- [ ] **Шаг 7: Коммит**

```bash
git add tools/gen_remnawave_models.py backend/core/src/repibot_core/integrations/remnawave backend/core/tests/test_remnawave_types.py
git commit -m "feat: модели панели Remnawave 3.2.1 и устойчивые псевдонимы типов"
```

---

### Задача 2: Домен подписок

**Файлы:**
- Создать: `backend/core/src/repibot_core/domain/subscriptions.py`
- Тест: `backend/core/tests/test_domain_subscriptions.py`

**Интерфейсы:**
- Отдаёт: `SubscriptionState` (StrEnum: `trial`, `active`, `expired`, `disabled`, `pending_provision`), `panel_username(user_id: int) -> str`, `extend(expires_at: datetime | None, now: datetime, days: int) -> datetime`, `convert_remainder(*, expires_at: datetime, now: datetime, current_price_rub: Decimal, current_duration_days: int, new_price_rub: Decimal, new_duration_days: int) -> int`, `resolve_state(*, expires_at: datetime, now: datetime, disabled: bool, provisioned: bool, is_trial: bool) -> SubscriptionState`.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_domain_subscriptions.py
"""Правила начисления дней. Без БД и сети."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from repibot_core.domain.subscriptions import (
    SubscriptionState,
    convert_remainder,
    extend,
    panel_username,
    resolve_state,
)

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


def test_username_is_short_and_allowed_by_panel() -> None:
    """Панель принимает 3–36 символов из букв, цифр, дефиса и подчёркивания."""
    assert panel_username(1) == "rp_1"
    assert panel_username(1_000_000) == "rp_lfls"


def test_extend_from_expiry_when_active() -> None:
    """Активная подписка продлевается от даты окончания: оплаченное не теряется."""
    expires = NOW + timedelta(days=5)
    assert extend(expires, NOW, 30) == expires + timedelta(days=30)


def test_extend_from_now_when_expired() -> None:
    """Истёкшая — от текущего момента, иначе покупка уходит в прошлое."""
    expires = NOW - timedelta(days=10)
    assert extend(expires, NOW, 30) == NOW + timedelta(days=30)


def test_extend_from_now_when_no_subscription() -> None:
    assert extend(None, NOW, 7) == NOW + timedelta(days=7)


def test_convert_remainder_scales_by_daily_price() -> None:
    """20 дней по 10 ₽/день — это 200 ₽, то есть 10 дней по 20 ₽/день."""
    days = convert_remainder(
        expires_at=NOW + timedelta(days=20),
        now=NOW,
        current_price_rub=Decimal("300.00"),
        current_duration_days=30,
        new_price_rub=Decimal("600.00"),
        new_duration_days=30,
    )
    assert days == 10


def test_convert_remainder_is_zero_for_expired() -> None:
    days = convert_remainder(
        expires_at=NOW - timedelta(days=1),
        now=NOW,
        current_price_rub=Decimal("300.00"),
        current_duration_days=30,
        new_price_rub=Decimal("300.00"),
        new_duration_days=30,
    )
    assert days == 0


def test_convert_remainder_rejects_free_plan() -> None:
    """Стоимость дня триала — ноль, делить на неё нечего."""
    with pytest.raises(ValueError, match="нулевая"):
        convert_remainder(
            expires_at=NOW + timedelta(days=5),
            now=NOW,
            current_price_rub=Decimal("300.00"),
            current_duration_days=30,
            new_price_rub=Decimal("0.00"),
            new_duration_days=7,
        )


@pytest.mark.parametrize(
    ("delta_days", "disabled", "provisioned", "is_trial", "expected"),
    [
        (10, False, True, False, SubscriptionState.active),
        (10, False, True, True, SubscriptionState.trial),
        (10, False, False, False, SubscriptionState.pending_provision),
        (10, True, True, False, SubscriptionState.disabled),
        (-1, False, True, True, SubscriptionState.expired),
        (-1, True, True, False, SubscriptionState.disabled),
    ],
)
def test_resolve_state(
    delta_days: int, disabled: bool, provisioned: bool, is_trial: bool, expected: SubscriptionState
) -> None:
    state = resolve_state(
        expires_at=NOW + timedelta(days=delta_days),
        now=NOW,
        disabled=disabled,
        provisioned=provisioned,
        is_trial=is_trial,
    )
    assert state is expected
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_domain_subscriptions.py -q`
Ожидание: FAIL, `ModuleNotFoundError: repibot_core.domain.subscriptions`

- [ ] **Шаг 3: Написать домен**

```python
# backend/core/src/repibot_core/domain/subscriptions.py
"""Правила подписки: сдвиг даты, конвертация остатка, состояние.

Чистые функции без БД и сети. Дату окончания двигает только этот модуль —
чтобы правило продления было записано ровно один раз и совпадало у бота,
MiniApp и веба.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
USERNAME_PREFIX = "rp_"


class SubscriptionState(StrEnum):
    trial = "trial"
    active = "active"
    expired = "expired"
    disabled = "disabled"
    pending_provision = "pending_provision"


def panel_username(user_id: int) -> str:
    """Имя пользователя в панели: `rp_` и наш идентификатор в base36.

    Панель ограничивает имя 36 символами и алфавитом без знаков препинания.
    base36 держит имя коротким и обратимым: по нему пользователь находится
    через resolve, если мы потеряли числовой идентификатор панели.
    """
    if user_id <= 0:
        msg = "идентификатор пользователя должен быть положительным"
        raise ValueError(msg)

    digits = ""
    value = user_id
    while value:
        value, remainder = divmod(value, len(ALPHABET))
        digits = ALPHABET[remainder] + digits
    return f"{USERNAME_PREFIX}{digits}"


def extend(expires_at: datetime | None, now: datetime, days: int) -> datetime:
    """Новая дата окончания после начисления дней.

    Активная подписка сдвигается от своей даты окончания, истёкшая и
    отсутствующая — от текущего момента. Иначе продление за день до конца
    съедало бы оплаченный остаток.
    """
    if days <= 0:
        msg = "число дней должно быть положительным"
        raise ValueError(msg)
    base = expires_at if expires_at is not None and expires_at > now else now
    return base + timedelta(days=days)


def convert_remainder(
    *,
    expires_at: datetime,
    now: datetime,
    current_price_rub: Decimal,
    current_duration_days: int,
    new_price_rub: Decimal,
    new_duration_days: int,
) -> int:
    """Остаток текущего тарифа в днях нового.

    Считается через стоимость дня: остаток превращается в деньги по цене дня
    текущего тарифа и делится на цену дня нового. Возвраты при смене тарифа
    тогда не нужны — оплаченное переезжает целиком.

    Дробный день отбрасывается: округление вверх позволяло бы бесконечно
    доливать время переключением туда-обратно.
    """
    if new_price_rub <= 0 or new_duration_days <= 0:
        msg = "у нового тарифа нулевая стоимость дня — конвертировать не во что"
        raise ValueError(msg)

    remaining = (expires_at - now).total_seconds() / timedelta(days=1).total_seconds()
    if remaining <= 0:
        return 0

    current_daily = current_price_rub / current_duration_days
    new_daily = new_price_rub / new_duration_days
    return int(Decimal(remaining) * current_daily / new_daily)


def resolve_state(
    *,
    expires_at: datetime,
    now: datetime,
    disabled: bool,
    provisioned: bool,
    is_trial: bool,
) -> SubscriptionState:
    """Состояние подписки одним правилом на все интерфейсы.

    Порядок проверок важен: снятый админом доступ виден и при живой дате,
    а невыданный доступ — не то же самое, что истёкший.
    """
    if disabled:
        return SubscriptionState.disabled
    if not provisioned:
        return SubscriptionState.pending_provision
    if expires_at <= now:
        return SubscriptionState.expired
    return SubscriptionState.trial if is_trial else SubscriptionState.active
```

- [ ] **Шаг 4: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/core/tests/test_domain_subscriptions.py -q`
Ожидание: PASS, 12 тестов

- [ ] **Шаг 5: Коммит**

```bash
git add backend/core/src/repibot_core/domain/subscriptions.py backend/core/tests/test_domain_subscriptions.py
git commit -m "feat: правила продления, конвертации остатка и состояния подписки"
```

---

### Задача 3: Таблицы подписок

**Файлы:**
- Создать: `backend/core/src/repibot_core/db/models/plan.py`
- Создать: `backend/core/src/repibot_core/db/models/subscription.py`
- Создать: `backend/core/src/repibot_core/db/models/trial.py`
- Изменить: `backend/core/src/repibot_core/db/models/__init__.py`
- Изменить: `backend/core/src/repibot_core/db/models/user.py`
- Создать: `backend/core/src/repibot_core/db/migrations/versions/0004_subscriptions.py`
- Тест: `backend/core/tests/test_subscription_models.py`

**Интерфейсы:**
- Отдаёт: `Plan`, `TrafficResetStrategy`, `Subscription`, `SubscriptionActor`, `SubscriptionSource`, `SubscriptionEvent`, `SubscriptionEventType`, `TrialGrant` — экспортируются из `repibot_core.db.models`. У `User` появляются `remnawave_id: int | None` и `remnawave_subscription_url: str | None`, поле `remnawave_uuid` исчезает.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_subscription_models.py
"""Схема подписок: ограничения, которые должна держать база."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Plan, Subscription, TrafficResetStrategy, TrialGrant, User
from repibot_core.domain.subscriptions import SubscriptionState

pytestmark = pytest.mark.docker


async def _plan(session: AsyncSession, *, code: str, is_trial: bool = False) -> Plan:
    plan = Plan(
        code=code,
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("299.00"),
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=3,
        internal_squad_uuids=["11111111-1111-4111-8111-111111111111"],
        is_trial=is_trial,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )
    session.add(plan)
    await session.flush()
    return plan


async def _user(session: AsyncSession, *, code: str) -> User:
    user = User(email=f"{code}@example.org", referral_code=code)
    session.add(user)
    await session.flush()
    return user


async def test_user_has_numeric_panel_id(db_session: AsyncSession) -> None:
    """В панели 3.2.1 пользователь адресуется числом, а не uuid."""
    user = await _user(db_session, code="ref00001")
    user.remnawave_id = 4_294_967_296
    await db_session.flush()
    assert user.remnawave_id == 4_294_967_296


async def test_one_subscription_per_user(db_session: AsyncSession) -> None:
    user = await _user(db_session, code="ref00002")
    plan = await _plan(db_session, code="month")
    now = datetime.now(UTC)

    for _ in range(2):
        db_session.add(
            Subscription(
                user_id=user.id,
                plan_id=plan.id,
                status=SubscriptionState.active,
                started_at=now,
                expires_at=now + timedelta(days=30),
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_only_one_active_trial_plan(db_session: AsyncSession) -> None:
    """Два активных триальных тарифа — неоднозначность, которую база не пропустит."""
    await _plan(db_session, code="trial-a", is_trial=True)
    await _plan(db_session, code="trial-b", is_trial=True)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_trial_grant_survives_user_deletion(db_session: AsyncSession) -> None:
    """Иначе триал накручивается удалением аккаунта и повторной регистрацией."""
    user = await _user(db_session, code="ref00003")
    db_session.add(TrialGrant(telegram_id=555, user_id=user.id))
    await db_session.flush()

    await db_session.delete(user)
    await db_session.flush()

    grant = await db_session.get(TrialGrant, 555)
    assert grant is not None
    assert grant.user_id is None
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_subscription_models.py -q`
Ожидание: FAIL, `ImportError: cannot import name 'Plan'`

- [ ] **Шаг 3: Написать модель тарифа**

```python
# backend/core/src/repibot_core/db/models/plan.py
"""Тариф: набор Internal Squad плюс лимиты и цена."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, Enum, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin


class TrafficResetStrategy(StrEnum):
    """Значения совпадают с панелью: они уходят в неё без преобразования."""

    NO_RESET = "NO_RESET"
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    MONTH_ROLLING = "MONTH_ROLLING"


class Plan(TimestampMixin, Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)

    # По локалям: {"ru": "…", "en": "…"}. Отдельные колонки под язык пришлось бы
    # добавлять миграцией на каждый новый язык.
    name: Mapped[dict[str, str]] = mapped_column(JSONB)
    description: Mapped[dict[str, str] | None] = mapped_column(JSONB)

    duration_days: Mapped[int] = mapped_column(Integer)
    # Numeric, а не float: YooKassa принимает сумму строкой «299.00», и
    # двоичная дробь здесь превращается в расхождение с чеком.
    price_rub: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    price_stars: Mapped[int] = mapped_column(Integer)

    traffic_limit_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    traffic_reset_strategy: Mapped[TrafficResetStrategy] = mapped_column(
        Enum(TrafficResetStrategy, name="traffic_reset_strategy", native_enum=True),
        default=TrafficResetStrategy.NO_RESET,
    )
    hwid_device_limit: Mapped[int] = mapped_column(Integer, default=0)
    internal_squad_uuids: Mapped[list[str]] = mapped_column(ARRAY(PgUUID(as_uuid=False)))

    is_trial: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
```

- [ ] **Шаг 4: Написать модели подписки и журнала**

```python
# backend/core/src/repibot_core/db/models/subscription.py
"""Подписка пользователя и журнал начислений."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin
from repibot_core.domain.subscriptions import SubscriptionState


class SubscriptionSource(StrEnum):
    trial = "trial"
    purchase = "purchase"
    gift = "gift"
    admin = "admin"


class SubscriptionEventType(StrEnum):
    trial = "trial"
    purchase = "purchase"
    renew = "renew"
    plan_change = "plan_change"
    bonus_days = "bonus_days"
    gift = "gift"
    expired = "expired"
    admin_grant = "admin_grant"
    admin_revoke = "admin_revoke"


class SubscriptionActor(StrEnum):
    user = "user"
    admin = "admin"
    system = "system"


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Одна подписка на пользователя: одна ссылка навсегда, как решено
    # архитектурой. Подарки добавляют дни, а не вторую строку.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))

    status: Mapped[SubscriptionState] = mapped_column(
        Enum(SubscriptionState, name="subscription_status", native_enum=True)
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    auto_renew_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[SubscriptionSource] = mapped_column(
        Enum(SubscriptionSource, name="subscription_source", native_enum=True)
    )


class SubscriptionEvent(Base):
    """Журнал начислений.

    Текущее состояние читается из subscriptions одним запросом, а разбор
    спорного случая — отсюда. Одно без другого не работает: состояние не
    помнит происхождения дней, журнал не отвечает, сколько осталось.
    """

    __tablename__ = "subscription_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[SubscriptionEventType] = mapped_column(
        Enum(SubscriptionEventType, name="subscription_event_type", native_enum=True)
    )
    days_delta: Mapped[int] = mapped_column(Integer)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"))
    actor: Mapped[SubscriptionActor] = mapped_column(
        Enum(SubscriptionActor, name="subscription_actor", native_enum=True)
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    comment: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

`created_at` здесь объявлен явно, без `TimestampMixin`: у журнальной записи нет момента изменения, а `updated_at` в неизменяемой таблице только вводит в заблуждение. Значение проставляет сервис.

- [ ] **Шаг 5: Написать модель выданных триалов**

```python
# backend/core/src/repibot_core/db/models/trial.py
"""Выданные триалы. Живут отдельно от пользователя и переживают его удаление."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base


class TrialGrant(Base):
    """Ключ — идентификатор Telegram, а не наш пользователь.

    Флаг на самом пользователе обходится удалением аккаунта и повторной
    регистрацией. Почту накрутить тривиально, поэтому и она ключом не годится.
    """

    __tablename__ = "trial_grants"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
```

- [ ] **Шаг 6: Обновить пользователя и экспорт моделей**

В `db/models/user.py` заменить два последних поля и убрать ставшие лишними импорты `UUID` и `PgUUID`:

```python
    # Панель 3.2.1 адресует пользователя числом; поля uuid у него больше нет.
    # BigInteger с запасом: идентификатор растёт с каждым созданным в панели
    # пользователем, включая заведённых мимо нас.
    remnawave_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    remnawave_short_uuid: Mapped[str | None] = mapped_column(String(64))
    # Ссылка подписки приходит из панели и обновляется на каждом примирении.
    # Собирать её из REMNAWAVE_BASE_URL нельзя: публичный домен подписки
    # настраивается в панели отдельно, а revoke меняет shortUuid.
    remnawave_subscription_url: Mapped[str | None] = mapped_column(String(512))
```

В `db/models/__init__.py` добавить импорты и записи в `__all__` для `Plan`, `TrafficResetStrategy`, `Subscription`, `SubscriptionActor`, `SubscriptionEvent`, `SubscriptionEventType`, `SubscriptionSource`, `TrialGrant`. Список `__all__` держать отсортированным — иначе ruff ругается правилом `RUF022`.

- [ ] **Шаг 7: Написать миграцию**

```python
# backend/core/src/repibot_core/db/migrations/versions/0004_subscriptions.py
"""Тарифы, подписки, журнал начислений, выданные триалы.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TRAFFIC_STRATEGY = sa.Enum(
    "NO_RESET", "DAY", "WEEK", "MONTH", "MONTH_ROLLING", name="traffic_reset_strategy"
)
SUBSCRIPTION_STATUS = sa.Enum(
    "trial", "active", "expired", "disabled", "pending_provision", name="subscription_status"
)
SUBSCRIPTION_SOURCE = sa.Enum("trial", "purchase", "gift", "admin", name="subscription_source")
SUBSCRIPTION_ACTOR = sa.Enum("user", "admin", "system", name="subscription_actor")
EVENT_TYPE = sa.Enum(
    "trial",
    "purchase",
    "renew",
    "plan_change",
    "bonus_days",
    "gift",
    "expired",
    "admin_grant",
    "admin_revoke",
    name="subscription_event_type",
)


def upgrade() -> None:
    # Панель 3.2.1 адресует пользователя числом. Данных в поле ещё нет —
    # подписки не выдавались, — поэтому колонка заменяется, а не переносится.
    op.drop_column("users", "remnawave_uuid")
    op.add_column("users", sa.Column("remnawave_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "users", sa.Column("remnawave_subscription_url", sa.String(512), nullable=True)
    )
    op.create_unique_constraint("uq_users_remnawave_id", "users", ["remnawave_id"])

    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", postgresql.JSONB(), nullable=False),
        sa.Column("description", postgresql.JSONB(), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("price_rub", sa.Numeric(10, 2), nullable=False),
        sa.Column("price_stars", sa.Integer(), nullable=False),
        sa.Column("traffic_limit_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("traffic_reset_strategy", TRAFFIC_STRATEGY, nullable=False),
        sa.Column("hwid_device_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "internal_squad_uuids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=False)),
            nullable=False,
        ),
        sa.Column("is_trial", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    # Активный триальный тариф ровно один: иначе «какой триал выдать» —
    # вопрос без ответа. Условие индекса оставляет в нём только такие строки,
    # и уникальность по is_trial означает «строка ровно одна».
    op.create_index(
        "uq_plans_single_active_trial",
        "plans",
        ["is_trial"],
        unique=True,
        postgresql_where=sa.text("is_trial AND is_active"),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("status", SUBSCRIPTION_STATUS, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "auto_renew_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("source", SUBSCRIPTION_SOURCE, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    # Крон истечения выбирает по дате и статусу — без индекса это полный
    # проход по таблице каждый час.
    op.create_index("ix_subscriptions_expires_at", "subscriptions", ["status", "expires_at"])

    op.create_table(
        "subscription_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", EVENT_TYPE, nullable=False),
        sa.Column("days_delta", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=True),
        sa.Column("actor", SUBSCRIPTION_ACTOR, nullable=False),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("comment", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_subscription_events_user_id", "subscription_events", ["user_id", "created_at"]
    )

    op.create_table(
        "trial_grants",
        sa.Column("telegram_id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("trial_grants")
    op.drop_index("ix_subscription_events_user_id", table_name="subscription_events")
    op.drop_table("subscription_events")
    op.drop_index("ix_subscriptions_expires_at", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_index("uq_plans_single_active_trial", table_name="plans")
    op.drop_table("plans")

    op.drop_constraint("uq_users_remnawave_id", "users", type_="unique")
    op.drop_column("users", "remnawave_subscription_url")
    op.drop_column("users", "remnawave_id")
    op.add_column("users", sa.Column("remnawave_uuid", postgresql.UUID(as_uuid=True), nullable=True))

    for enum_type in (EVENT_TYPE, SUBSCRIPTION_ACTOR, SUBSCRIPTION_SOURCE, SUBSCRIPTION_STATUS,
                      TRAFFIC_STRATEGY):
        enum_type.drop(op.get_bind(), checkfirst=True)
```

- [ ] **Шаг 8: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/core/tests/test_subscription_models.py -q`
Ожидание: PASS, 4 теста. Фикстура `db_session` сама прогоняет `downgrade base` и `upgrade head`, то есть обратная миграция проверяется каждым запуском.

- [ ] **Шаг 9: Коммит**

```bash
git add backend/core/src/repibot_core/db backend/core/tests/test_subscription_models.py
git commit -m "feat: таблицы тарифов, подписок, журнала начислений и триалов"
```

---

### Задача 4: Настройки этапа

**Файлы:**
- Изменить: `backend/core/src/repibot_core/settings.py`
- Изменить: `.env.example`
- Изменить: `docs/deployment.md`
- Тест: `backend/core/tests/test_settings_subscriptions.py`

**Интерфейсы:**
- Отдаёт: поля `Settings.remnawave_webhook_secret`, `remnawave_webhook_header`, `remnawave_provision_timeout_seconds`, `panel_cache_ttl_seconds`, `device_unlink_limit_per_day`, `plan_change_keeps_remainder`, `reconcile_interval_hours`.

Переменные заводятся все сразу, включая те, что понадобятся этапу 2b: `settings.py`, `.env.example` и `docs/deployment.md` — файлы, за которые параллельные исполнители дерутся, и трогать их лучше один раз.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_settings_subscriptions.py
"""Значения по умолчанию для настроек подписок."""

from __future__ import annotations

from repibot_core.settings import Settings


def test_defaults_are_safe() -> None:
    settings = Settings()  # type: ignore[call-arg]

    # Пустой секрет означает «вебхуки не настроены»: принимать неподписанные
    # события опаснее, чем не принимать никаких.
    assert settings.remnawave_webhook_secret.get_secret_value() == ""
    assert settings.remnawave_webhook_header == "x-remnawave-signature"
    # Синхронная попытка короче обычного таймаута клиента: пользователь ждёт
    # ответа, а надёжность обеспечивает очередь, а не терпение.
    assert settings.remnawave_provision_timeout_seconds == 3.0
    assert settings.panel_cache_ttl_seconds == 60
    assert settings.device_unlink_limit_per_day == 10
    assert settings.plan_change_keeps_remainder is True
    assert settings.reconcile_interval_hours == 6
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_settings_subscriptions.py -q`
Ожидание: FAIL, `AttributeError: 'Settings' object has no attribute 'remnawave_webhook_secret'`

- [ ] **Шаг 3: Добавить поля в настройки**

В `settings.py` после блока `remnawave_max_attempts`:

```python
    # Секрет и имя заголовка задаются на стороне панели. Имя вынесено в
    # настройку, потому что в схеме панели его нет: вебхуки исходящие, и
    # подтвердить заголовок можно только на живой панели.
    remnawave_webhook_secret: SecretStr = SecretStr("")
    remnawave_webhook_header: str = "x-remnawave-signature"
    # Синхронная попытка выдачи доступа. Короче обычного таймаута клиента:
    # надёжность даёт очередь, а не ожидание пользователя.
    remnawave_provision_timeout_seconds: float = 3.0

    panel_cache_ttl_seconds: int = 60
    device_unlink_limit_per_day: int = 10
    plan_change_keeps_remainder: bool = True
    reconcile_interval_hours: int = 6
```

- [ ] **Шаг 4: Дописать `.env.example` и документацию**

В `.env.example` добавить блок с теми же значениями и комментариями на русском. В `docs/deployment.md` — строки таблицы переменных с колонками «переменная», «по умолчанию», «назначение», следуя формату уже описанных там переменных.

- [ ] **Шаг 5: Запустить тесты**

Запуск: `uv run pytest backend/core/tests/test_settings_subscriptions.py -q && uv run pytest tools/tests/test_docs.py -q`
Ожидание: PASS. Второй набор проверяет, что документация не разошлась с `.env.example`.

- [ ] **Шаг 6: Коммит**

```bash
git add backend/core/src/repibot_core/settings.py .env.example docs/deployment.md backend/core/tests/test_settings_subscriptions.py
git commit -m "feat: настройки вебхуков панели, кэша и реконсиляции"
```

---

### Задача 5: Репозитории тарифов, подписок и триалов

**Файлы:**
- Создать: `backend/core/src/repibot_core/db/repositories/plans.py`
- Создать: `backend/core/src/repibot_core/db/repositories/subscriptions.py`
- Создать: `backend/core/src/repibot_core/db/repositories/trials.py`
- Изменить: `backend/core/src/repibot_core/db/repositories/__init__.py`
- Тест: `backend/core/tests/test_subscription_repositories.py`

**Интерфейсы:**
- Потребляет: `Plan`, `Subscription`, `SubscriptionEvent`, `TrialGrant` из задачи 3.
- Отдаёт:
  - `PlanRepository(session)`: `list_all()`, `list_visible()`, `get(plan_id)`, `get_by_code(code)`, `active_trial()`, `create(**fields) -> Plan`, `archive(plan) -> None`.
  - `SubscriptionRepository(session)`: `get_for_user(user_id)`, `create(**fields) -> Subscription`, `list_due(now, limit) -> list[Subscription]`, `list_for_reconcile(limit) -> list[Subscription]`, `add_event(**fields) -> SubscriptionEvent`.
  - `TrialRepository(session)`: `get(telegram_id)`, `create(telegram_id, user_id) -> TrialGrant`.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_subscription_repositories.py
"""Выборки, на которые опираются сервисы."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import SubscriptionSource, TrafficResetStrategy, User
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.db.repositories.trials import TrialRepository
from repibot_core.domain.subscriptions import SubscriptionState

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"


def _plan_fields(code: str, **overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "code": code,
        "name": {"ru": code, "en": code},
        "description": None,
        "duration_days": 30,
        "price_rub": Decimal("299.00"),
        "price_stars": 199,
        "traffic_limit_bytes": 0,
        "traffic_reset_strategy": TrafficResetStrategy.NO_RESET,
        "hwid_device_limit": 3,
        "internal_squad_uuids": [SQUAD],
        "is_trial": False,
        "is_active": True,
        "is_visible": True,
        "sort_order": 0,
    }
    fields.update(overrides)
    return fields


async def test_visible_plans_are_sorted_and_filtered(db_session: AsyncSession) -> None:
    plans = PlanRepository(db_session)
    await plans.create(**_plan_fields("second", sort_order=2))
    await plans.create(**_plan_fields("first", sort_order=1))
    await plans.create(**_plan_fields("hidden", is_visible=False))
    await plans.create(**_plan_fields("archived", is_active=False))

    codes = [plan.code for plan in await plans.list_visible()]
    assert codes == ["first", "second"]


async def test_archive_keeps_row(db_session: AsyncSession) -> None:
    """Тариф не удаляется: на него ссылаются подписки и журнал."""
    plans = PlanRepository(db_session)
    plan = await plans.create(**_plan_fields("month"))
    await plans.archive(plan)

    assert await plans.get(plan.id) is not None
    assert await plans.list_visible() == []


async def test_active_trial_returns_only_trial(db_session: AsyncSession) -> None:
    plans = PlanRepository(db_session)
    await plans.create(**_plan_fields("month"))
    trial = await plans.create(**_plan_fields("trial", is_trial=True, duration_days=3))

    found = await plans.active_trial()
    assert found is not None
    assert found.id == trial.id


async def test_list_due_selects_only_expired_working_subscriptions(
    db_session: AsyncSession,
) -> None:
    plans = PlanRepository(db_session)
    plan = await plans.create(**_plan_fields("month"))
    subscriptions = SubscriptionRepository(db_session)
    now = datetime.now(UTC)

    for index, (state, delta) in enumerate(
        [
            (SubscriptionState.active, -1),
            (SubscriptionState.trial, -1),
            (SubscriptionState.active, 5),
            (SubscriptionState.expired, -10),
        ]
    ):
        user = User(email=f"due{index}@example.org", referral_code=f"due{index:05d}")
        db_session.add(user)
        await db_session.flush()
        await subscriptions.create(
            user_id=user.id,
            plan_id=plan.id,
            status=state,
            started_at=now - timedelta(days=30),
            expires_at=now + timedelta(days=delta),
            source=SubscriptionSource.purchase,
        )

    due = await subscriptions.list_due(now=now, limit=100)
    assert {row.status for row in due} == {SubscriptionState.active, SubscriptionState.trial}
    assert len(due) == 2


async def test_trial_grant_is_found_by_telegram_id(db_session: AsyncSession) -> None:
    trials = TrialRepository(db_session)
    assert await trials.get(777) is None
    await trials.create(telegram_id=777, user_id=None)
    assert await trials.get(777) is not None
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_subscription_repositories.py -q`
Ожидание: FAIL, `ModuleNotFoundError: repibot_core.db.repositories.plans`

- [ ] **Шаг 3: Написать репозиторий тарифов**

```python
# backend/core/src/repibot_core/db/repositories/plans.py
"""Доступ к тарифам."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Plan


class PlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, plan_id: int) -> Plan | None:
        return await self._session.get(Plan, plan_id)

    async def get_by_code(self, code: str) -> Plan | None:
        statement = select(Plan).where(Plan.code == code)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_all(self) -> list[Plan]:
        statement = select(Plan).order_by(Plan.sort_order, Plan.id)
        return list((await self._session.execute(statement)).scalars())

    async def list_visible(self) -> list[Plan]:
        statement = (
            select(Plan)
            .where(Plan.is_active.is_(True), Plan.is_visible.is_(True))
            .order_by(Plan.sort_order, Plan.id)
        )
        return list((await self._session.execute(statement)).scalars())

    async def active_trial(self) -> Plan | None:
        statement = select(Plan).where(Plan.is_trial.is_(True), Plan.is_active.is_(True))
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def create(self, **fields: Any) -> Plan:
        plan = Plan(**fields)
        self._session.add(plan)
        await self._session.flush()
        return plan

    async def archive(self, plan: Plan) -> None:
        """Снимает тариф с продажи, не удаляя строку.

        Физическое удаление порвало бы ссылки из подписок и журнала
        начислений, а в подпроекте 3 — ещё и из платежей.
        """
        plan.is_active = False
        await self._session.flush()
```

- [ ] **Шаг 4: Написать репозитории подписок и триалов**

```python
# backend/core/src/repibot_core/db/repositories/subscriptions.py
"""Доступ к подпискам и журналу начислений."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Subscription, SubscriptionEvent
from repibot_core.domain.subscriptions import SubscriptionState

# Статусы, при которых подписка должна существовать в панели.
WORKING_STATES = (
    SubscriptionState.trial,
    SubscriptionState.active,
    SubscriptionState.pending_provision,
)


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_user(self, user_id: int) -> Subscription | None:
        statement = select(Subscription).where(Subscription.user_id == user_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def create(self, **fields: Any) -> Subscription:
        subscription = Subscription(**fields)
        self._session.add(subscription)
        await self._session.flush()
        return subscription

    async def list_due(self, *, now: datetime, limit: int) -> list[Subscription]:
        """Подписки, срок которых вышел, но статус ещё рабочий."""
        statement = (
            select(Subscription)
            .where(
                Subscription.status.in_(
                    [SubscriptionState.trial, SubscriptionState.active]
                ),
                Subscription.expires_at <= now,
            )
            .order_by(Subscription.expires_at)
            .limit(limit)
        )
        return list((await self._session.execute(statement)).scalars())

    async def list_for_reconcile(self, *, limit: int, after_id: int = 0) -> list[Subscription]:
        """Страница подписок для сверки с панелью.

        Курсор по идентификатору, а не OFFSET: прогон идёт долго, и сдвиг
        страницы из-за вставки новой подписки пропустил бы чужую строку.
        """
        statement = (
            select(Subscription)
            .where(Subscription.status.in_(WORKING_STATES), Subscription.id > after_id)
            .order_by(Subscription.id)
            .limit(limit)
        )
        return list((await self._session.execute(statement)).scalars())

    async def add_event(self, **fields: Any) -> SubscriptionEvent:
        event = SubscriptionEvent(**fields)
        self._session.add(event)
        await self._session.flush()
        return event
```

```python
# backend/core/src/repibot_core/db/repositories/trials.py
"""Доступ к выданным триалам."""

from __future__ import annotations

from repibot_core.db.models import TrialGrant
from sqlalchemy.ext.asyncio import AsyncSession


class TrialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, telegram_id: int) -> TrialGrant | None:
        return await self._session.get(TrialGrant, telegram_id)

    async def create(self, *, telegram_id: int, user_id: int | None) -> TrialGrant:
        grant = TrialGrant(telegram_id=telegram_id, user_id=user_id)
        self._session.add(grant)
        await self._session.flush()
        return grant
```

Импорты в файле выше расставить в порядке, который требует ruff (`repibot_core` после сторонних пакетов) — приведённый порядок исправит `ruff format`.

- [ ] **Шаг 5: Дописать экспорт**

В `db/repositories/__init__.py` добавить `PlanRepository`, `SubscriptionRepository`, `TrialRepository` по образцу уже перечисленных там репозиториев.

- [ ] **Шаг 6: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/core/tests/test_subscription_repositories.py -q`
Ожидание: PASS, 5 тестов

- [ ] **Шаг 7: Коммит**

```bash
git add backend/core/src/repibot_core/db/repositories backend/core/tests/test_subscription_repositories.py
git commit -m "feat: репозитории тарифов, подписок и триалов"
```

---

### Задача 6: Фасады панели

**Файлы:**
- Изменить: `backend/core/src/repibot_core/integrations/remnawave/client.py`
- Создать: `backend/core/src/repibot_core/integrations/remnawave/users.py`
- Создать: `backend/core/src/repibot_core/integrations/remnawave/squads.py`
- Изменить: `backend/core/src/repibot_core/integrations/remnawave/__init__.py`
- Тест: `backend/core/tests/test_remnawave_facades.py`

**Интерфейсы:**
- Потребляет: `PanelUser`, `PanelSquad`, `CreateUserBody`, `UpdateUserBody` из задачи 1; `Settings` из задачи 4.
- Отдаёт:
  - `RemnawaveClient(base_url, token, timeout, max_attempts, transport=None)` — новый необязательный параметр `transport`.
  - `PanelUsers(client)`: `get(user_id) -> PanelUser | None`, `resolve(*, panel_id=None, short_uuid=None, username=None) -> PanelUser | None`, `create(body: CreateUserBody) -> PanelUser`, `update(body: UpdateUserBody) -> PanelUser`.
  - `PanelSquads(client)`: `list() -> list[PanelSquad]`.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_remnawave_facades.py
"""Фасады панели: адреса, тела запросов и разбор ответов."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from repibot_core.integrations.remnawave.client import RemnawaveClient
from repibot_core.integrations.remnawave.squads import PanelSquads
from repibot_core.integrations.remnawave.types import CreateUserBody
from repibot_core.integrations.remnawave.users import PanelUsers

USER_PAYLOAD: dict[str, Any] = {
    "id": 42,
    "shortUuid": "abc123",
    "username": "rp_1",
    "status": "ACTIVE",
    "trafficLimitBytes": 0,
    "trafficLimitStrategy": "NO_RESET",
    "expireAt": "2026-09-06T12:00:00Z",
    "telegramId": None,
    "email": None,
    "description": None,
    "tag": "REPIBOT",
    "hwidDeviceLimit": 3,
    "externalSquadUuid": None,
    "trojanPassword": "trojan-password",
    "vlessUuid": "11111111-1111-4111-8111-111111111111",
    "ssPassword": "ss-password",
    "lastTriggeredThreshold": 0,
    "subRevokedAt": None,
    "lastTrafficResetAt": None,
    "createdAt": "2026-08-06T12:00:00Z",
    "updatedAt": "2026-08-06T12:00:00Z",
    "subscriptionUrl": "https://panel.example.org/sub/abc123",
    "activeInternalSquads": [],
    "userTraffic": {
        "usedTrafficBytes": 0,
        "lifetimeUsedTrafficBytes": 0,
        "onlineAt": "2026-08-06T12:00:00Z",
        "firstConnectedAt": "2026-08-06T12:00:00Z",
        "lastConnectedNodeUuid": "22222222-2222-4222-8222-222222222222",
    },
}


def _client(handler: httpx.MockTransport) -> RemnawaveClient:
    return RemnawaveClient(
        base_url="https://panel.example.org", token="token", transport=handler
    )


async def test_user_with_null_fields_parses() -> None:
    """Панель присылает null в telegramId, email и tag — разбор не должен падать."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"response": USER_PAYLOAD})
    )
    user = await PanelUsers(_client(transport)).get(42)

    assert user is not None
    assert user.telegramId is None
    assert user.subscriptionUrl.endswith("/sub/abc123")


async def test_missing_user_is_none_not_error() -> None:
    """404 — обычный ответ «такого нет», а не отказ панели."""
    transport = httpx.MockTransport(lambda request: httpx.Response(404, json={}))
    assert await PanelUsers(_client(transport)).get(42) is None


async def test_resolve_sends_only_given_key() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"response": USER_PAYLOAD})

    await PanelUsers(_client(httpx.MockTransport(handler))).resolve(username="rp_1")

    assert seen["url"] == "https://panel.example.org/api/users/resolve"
    assert seen["body"] == '{"username":"rp_1"}'


async def test_update_goes_to_collection_with_id_in_body() -> None:
    """В 3.2.1 PATCH идёт на /api/users, идентификатор — в теле."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"response": USER_PAYLOAD})

    from repibot_core.integrations.remnawave.types import UpdateUserBody

    await PanelUsers(_client(httpx.MockTransport(handler))).update(
        UpdateUserBody(id=42, hwidDeviceLimit=5)
    )

    assert seen["method"] == "PATCH"
    assert seen["url"] == "https://panel.example.org/api/users"
    assert '"id":42' in seen["body"]
    assert '"hwidDeviceLimit":5' in seen["body"]


async def test_create_raises_on_rejection() -> None:
    """400 от панели — наша ошибка запроса, её нельзя проглотить."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(400, json={"message": "username taken"})
    )
    with pytest.raises(Exception, match="400"):
        await PanelUsers(_client(transport)).create(
            CreateUserBody(username="rp_1", expireAt="2026-09-06T12:00:00Z")
        )


async def test_squads_are_flattened() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "response": {
                    "total": 1,
                    "internalSquads": [
                        {
                            "uuid": "11111111-1111-4111-8111-111111111111",
                            "viewPosition": 0,
                            "name": "Европа",
                            "info": {"membersCount": 0, "inboundsCount": 1},
                            "inbounds": [],
                            "createdAt": "2026-08-06T12:00:00Z",
                            "updatedAt": "2026-08-06T12:00:00Z",
                        }
                    ],
                }
            },
        )
    )
    squads = await PanelSquads(_client(transport)).list()
    assert [squad.name for squad in squads] == ["Европа"]
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_remnawave_facades.py -q`
Ожидание: FAIL, `ModuleNotFoundError: repibot_core.integrations.remnawave.users`

- [ ] **Шаг 3: Разрешить подмену транспорта в клиенте**

В `client.py` добавить параметр и ошибку отказа запроса:

```python
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 10.0,
        max_attempts: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.max_attempts = max_attempts
        # Транспорт подменяется в тестах: заглушка отвечает за поведение
        # панели, а маршруты и тела запросов при этом проверяются настоящие.
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
            transport=transport,
        )
```

Туда же, рядом с `RemnawaveUnavailable`:

```python
class RemnawaveRejected(RemnawaveError):  # noqa: N818
    """Панель ответила осмысленным отказом: 4xx кроме 404."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"панель отклонила запрос: {status_code}")
        self.status_code = status_code
        self.body = body
```

В `create_remnawave_client` ничего не меняется: транспорт по умолчанию `None`.

- [ ] **Шаг 4: Написать фасад пользователей**

```python
# backend/core/src/repibot_core/integrations/remnawave/users.py
"""Пользователи панели.

Фасад знает адреса и формы запросов, но не знает, зачем их зовут. Решение
«создать или обновить» принимает сервис примирения.
"""

from __future__ import annotations

import httpx

from repibot_core.integrations.remnawave.client import RemnawaveClient, RemnawaveRejected
from repibot_core.integrations.remnawave.models import UserResponseDto
from repibot_core.integrations.remnawave.types import (
    CreateUserBody,
    PanelUser,
    ResolveUserBody,
    UpdateUserBody,
)


class PanelUsers:
    def __init__(self, client: RemnawaveClient) -> None:
        self._client = client

    async def get(self, panel_id: int) -> PanelUser | None:
        response = await self._client.request("GET", f"/api/users/{panel_id}")
        return self._one_or_none(response)

    async def resolve(
        self,
        *,
        panel_id: int | None = None,
        short_uuid: str | None = None,
        username: str | None = None,
    ) -> PanelUser | None:
        """Поиск пользователя по одному из трёх ключей.

        Заменяет удалённые в 3.2.1 маршруты by-email, by-telegram-id и by-tag.
        Пустые ключи не отправляются: панель различает «не задано» и «пусто».
        """
        body = ResolveUserBody(id=panel_id, shortUuid=short_uuid, username=username)
        response = await self._client.request(
            "POST", "/api/users/resolve", content=body.model_dump_json(exclude_none=True)
        )
        return self._one_or_none(response)

    async def create(self, body: CreateUserBody) -> PanelUser:
        response = await self._client.request(
            "POST", "/api/users", content=body.model_dump_json(exclude_none=True)
        )
        return self._one(response)

    async def update(self, body: UpdateUserBody) -> PanelUser:
        # В 3.2.1 обновление идёт на коллекцию, идентификатор — в теле.
        response = await self._client.request(
            "PATCH", "/api/users", content=body.model_dump_json(exclude_none=True)
        )
        return self._one(response)

    @staticmethod
    def _one(response: httpx.Response) -> PanelUser:
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise RemnawaveRejected(response.status_code, response.text[:500])
        return UserResponseDto.model_validate_json(response.content).response

    @classmethod
    def _one_or_none(cls, response: httpx.Response) -> PanelUser | None:
        # 404 — не отказ, а ответ «такого пользователя нет». Ошибкой его
        # делать нельзя: примирение на нём создаёт пользователя.
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        return cls._one(response)
```

Заголовок `Content-Type: application/json` при передаче `content=` нужно проставлять явно — добавить его в `RemnawaveClient.__init__` в общий словарь заголовков клиента.

- [ ] **Шаг 5: Написать фасад сквадов**

```python
# backend/core/src/repibot_core/integrations/remnawave/squads.py
"""Внутренние сквады панели — то, из чего собирается тариф."""

from __future__ import annotations

import httpx

from repibot_core.integrations.remnawave.client import RemnawaveClient, RemnawaveRejected
from repibot_core.integrations.remnawave.models import GetInternalSquadsResponseDto
from repibot_core.integrations.remnawave.types import PanelSquad


class PanelSquads:
    def __init__(self, client: RemnawaveClient) -> None:
        self._client = client

    async def list(self) -> list[PanelSquad]:
        response = await self._client.request("GET", "/api/internal-squads")
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise RemnawaveRejected(response.status_code, response.text[:500])
        return list(
            GetInternalSquadsResponseDto.model_validate_json(response.content).response.internalSquads
        )
```

В `integrations/remnawave/__init__.py` выставить наружу `PanelUsers`, `PanelSquads`, `RemnawaveClient`, `RemnawaveError`, `RemnawaveRejected`, `RemnawaveUnavailable`, `create_remnawave_client`.

- [ ] **Шаг 6: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/core/tests/test_remnawave_facades.py -q`
Ожидание: PASS, 6 тестов

- [ ] **Шаг 7: Коммит**

```bash
git add backend/core/src/repibot_core/integrations/remnawave backend/core/tests/test_remnawave_facades.py
git commit -m "feat: фасады пользователей и сквадов панели"
```

---

### Задача 7: Заглушка панели

**Файлы:**
- Создать: `backend/core/src/repibot_core/testing/remnawave.py`
- Изменить: `backend/core/src/repibot_core/testing/__init__.py`
- Тест: `backend/core/tests/test_fake_panel.py`

**Интерфейсы:**
- Потребляет: `RemnawaveClient` с параметром `transport` из задачи 6.
- Отдаёт: `FakePanel()` с полями `users: dict[int, dict[str, Any]]`, `squads: list[dict[str, Any]]`, `requests: list[tuple[str, str]]`; методами `client() -> RemnawaveClient`, `transport() -> httpx.MockTransport`, `add_squad(uuid, name) -> None`, `fail_next(times: int = 1) -> None`.

Заглушка держит пользователей в памяти и отвечает так же, как панель 3.2.1: числовой идентификатор, `resolve` по трём ключам, 404 на неизвестном. Она проверяет наш код, но не панель — поэтому в задаче 16 есть ручная проверка на живой.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_fake_panel.py
"""Заглушка должна вести себя как панель, иначе тесты сервисов ничего не значат."""

from __future__ import annotations

import pytest

from repibot_core.integrations.remnawave.client import RemnawaveUnavailable
from repibot_core.integrations.remnawave.types import CreateUserBody, UpdateUserBody
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.testing.remnawave import FakePanel


async def test_created_user_gets_numeric_id_and_subscription_url() -> None:
    panel = FakePanel()
    users = PanelUsers(panel.client())

    created = await users.create(
        CreateUserBody(username="rp_1", expireAt="2026-09-06T12:00:00Z", tag="REPIBOT")
    )

    assert isinstance(created.id, float | int)
    assert created.subscriptionUrl.endswith(created.shortUuid)
    assert created.tag == "REPIBOT"


async def test_resolve_finds_by_username_and_misses_unknown() -> None:
    panel = FakePanel()
    users = PanelUsers(panel.client())
    await users.create(CreateUserBody(username="rp_1", expireAt="2026-09-06T12:00:00Z"))

    assert await users.resolve(username="rp_1") is not None
    assert await users.resolve(username="rp_2") is None


async def test_update_changes_only_given_fields() -> None:
    panel = FakePanel()
    users = PanelUsers(panel.client())
    created = await users.create(
        CreateUserBody(username="rp_1", expireAt="2026-09-06T12:00:00Z", hwidDeviceLimit=3)
    )

    updated = await users.update(UpdateUserBody(id=int(created.id), hwidDeviceLimit=5))

    assert updated.hwidDeviceLimit == 5
    assert updated.username == "rp_1"


async def test_fail_next_makes_panel_unavailable() -> None:
    """Сценарий «панель лежит» нужен тестам провижининга."""
    panel = FakePanel()
    panel.fail_next(times=10)

    with pytest.raises(RemnawaveUnavailable):
        await PanelUsers(panel.client()).get(1)
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_fake_panel.py -q`
Ожидание: FAIL, `ModuleNotFoundError: repibot_core.testing.remnawave`

- [ ] **Шаг 3: Написать заглушку**

```python
# backend/core/src/repibot_core/testing/remnawave.py
"""Панель Remnawave 3.2.1 в памяти.

Подменяется транспорт, а не фасад: маршруты, методы и тела запросов при этом
проверяются настоящие. Заглушка повторяет форму ответов и правила поиска, но
не поведение живой панели — ручная проверка остаётся обязательной.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from repibot_core.integrations.remnawave.client import RemnawaveClient

BASE_URL = "https://panel.example.test"


class FakePanel:
    def __init__(self) -> None:
        self.users: dict[int, dict[str, Any]] = {}
        self.squads: list[dict[str, Any]] = []
        self.requests: list[tuple[str, str]] = []
        self._next_id = 1
        self._failures = 0

    # --- сборка ---

    def client(self) -> RemnawaveClient:
        # Одна попытка: тесту, проверяющему отказ, незачем ждать три захода
        # с экспоненциальной задержкой.
        return RemnawaveClient(
            base_url=BASE_URL, token="test", max_attempts=1, transport=self.transport()
        )

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def add_squad(self, uuid: str, name: str) -> None:
        self.squads.append(
            {
                "uuid": uuid,
                "viewPosition": len(self.squads),
                "name": name,
                "info": {"membersCount": 0, "inboundsCount": 0},
                "inbounds": [],
                "createdAt": _now(),
                "updatedAt": _now(),
            }
        )

    def fail_next(self, times: int = 1) -> None:
        """Следующие запросы отвечают 503 — панель «лежит»."""
        self._failures = times

    # --- обработка ---

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, request.url.path))

        if self._failures > 0:
            self._failures -= 1
            return httpx.Response(503, json={"message": "panel is down"})

        path = request.url.path
        if path == "/api/internal-squads":
            return httpx.Response(
                200, json={"response": {"total": len(self.squads), "internalSquads": self.squads}}
            )
        if path == "/api/users" and request.method == "POST":
            return self._create(json.loads(request.content))
        if path == "/api/users" and request.method == "PATCH":
            return self._update(json.loads(request.content))
        if path == "/api/users/resolve":
            return self._resolve(json.loads(request.content))
        if path.startswith("/api/users/"):
            return self._get(int(path.rsplit("/", 1)[-1]))

        return httpx.Response(404, json={"message": "not found"})

    def _create(self, body: dict[str, Any]) -> httpx.Response:
        if any(user["username"] == body["username"] for user in self.users.values()):
            return httpx.Response(400, json={"message": "username already exists"})

        panel_id = self._next_id
        self._next_id += 1
        short_uuid = uuid4().hex[:16]
        user = _template(panel_id, short_uuid, body)
        self.users[panel_id] = user
        return httpx.Response(200, json={"response": user})

    def _update(self, body: dict[str, Any]) -> httpx.Response:
        user = self.users.get(int(body["id"]))
        if user is None:
            return httpx.Response(404, json={"message": "not found"})
        for key, value in body.items():
            if key == "id":
                continue
            user[key] = value
        user["updatedAt"] = _now()
        return httpx.Response(200, json={"response": user})

    def _resolve(self, body: dict[str, Any]) -> httpx.Response:
        for user in self.users.values():
            if "id" in body and user["id"] == body["id"]:
                return httpx.Response(200, json={"response": user})
            if "shortUuid" in body and user["shortUuid"] == body["shortUuid"]:
                return httpx.Response(200, json={"response": user})
            if "username" in body and user["username"] == body["username"]:
                return httpx.Response(200, json={"response": user})
        return httpx.Response(404, json={"message": "not found"})

    def _get(self, panel_id: int) -> httpx.Response:
        user = self.users.get(panel_id)
        if user is None:
            return httpx.Response(404, json={"message": "not found"})
        return httpx.Response(200, json={"response": user})


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _template(panel_id: int, short_uuid: str, body: dict[str, Any]) -> dict[str, Any]:
    """Пользователь панели со всеми обязательными полями ответа."""
    return {
        "id": panel_id,
        "shortUuid": short_uuid,
        "username": body["username"],
        "status": body.get("status", "ACTIVE"),
        "trafficLimitBytes": body.get("trafficLimitBytes", 0),
        "trafficLimitStrategy": body.get("trafficLimitStrategy", "NO_RESET"),
        "expireAt": body["expireAt"],
        "telegramId": body.get("telegramId"),
        "email": body.get("email"),
        "description": body.get("description"),
        "tag": body.get("tag"),
        "hwidDeviceLimit": body.get("hwidDeviceLimit", 0),
        "externalSquadUuid": body.get("externalSquadUuid"),
        "trojanPassword": "trojan-password",
        "vlessUuid": str(uuid4()),
        "ssPassword": "ss-password",
        "lastTriggeredThreshold": 0,
        "subRevokedAt": None,
        "lastTrafficResetAt": None,
        "createdAt": _now(),
        "updatedAt": _now(),
        "subscriptionUrl": f"{BASE_URL}/sub/{short_uuid}",
        "activeInternalSquads": [
            {"uuid": uuid, "name": uuid} for uuid in body.get("activeInternalSquads", [])
        ],
        "userTraffic": {
            "usedTrafficBytes": 0,
            "lifetimeUsedTrafficBytes": 0,
            "onlineAt": _now(),
            "firstConnectedAt": _now(),
            "lastConnectedNodeUuid": str(uuid4()),
        },
    }
```

- [ ] **Шаг 4: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/core/tests/test_fake_panel.py -q`
Ожидание: PASS, 4 теста

- [ ] **Шаг 5: Коммит**

```bash
git add backend/core/src/repibot_core/testing backend/core/tests/test_fake_panel.py
git commit -m "test: заглушка панели Remnawave в памяти"
```

---

### Задача 8: Сервис тарифов

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/errors.py`
- Создать: `backend/core/src/repibot_core/services/plans.py`
- Тест: `backend/core/tests/test_plan_service.py`

**Интерфейсы:**
- Потребляет: `PlanRepository` (задача 5), `PanelSquads` (задача 6).
- Отдаёт:
  - `ServiceError(message, code)` — общий предок ошибок сервисов с полем `.code`.
  - `PlanInput` — dataclass с полями `code`, `name`, `description`, `duration_days`, `price_rub`, `price_stars`, `traffic_limit_bytes`, `traffic_reset_strategy`, `hwid_device_limit`, `internal_squad_uuids`, `is_trial`, `is_visible`, `sort_order`.
  - `PlanView` — dataclass с теми же полями плюс `id` и `is_active`.
  - `PlanService(session, squads)`: `visible() -> list[PlanView]`, `all() -> list[PlanView]`, `require(plan_id) -> Plan`, `create(data) -> PlanView`, `update(plan_id, data) -> PlanView`, `archive(plan_id) -> None`.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_plan_service.py
"""Тарифы: проверка сквадов, видимость, архивация."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import TrafficResetStrategy
from repibot_core.integrations.remnawave.squads import PanelSquads
from repibot_core.services.errors import ServiceError
from repibot_core.services.plans import PlanInput, PlanService
from repibot_core.testing.remnawave import FakePanel

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"


def _input(code: str, **overrides: object) -> PlanInput:
    data = {
        "code": code,
        "name": {"ru": "Месяц", "en": "Month"},
        "description": None,
        "duration_days": 30,
        "price_rub": Decimal("299.00"),
        "price_stars": 199,
        "traffic_limit_bytes": 0,
        "traffic_reset_strategy": TrafficResetStrategy.NO_RESET,
        "hwid_device_limit": 3,
        "internal_squad_uuids": [SQUAD],
        "is_trial": False,
        "is_visible": True,
        "sort_order": 0,
    }
    data.update(overrides)
    return PlanInput(**data)  # type: ignore[arg-type]


def _service(session: AsyncSession, panel: FakePanel) -> PlanService:
    return PlanService(session, PanelSquads(panel.client()))


async def test_plan_with_unknown_squad_is_rejected(db_session: AsyncSession) -> None:
    """Тариф со сквадом, которого нет в панели, продаётся и не работает."""
    panel = FakePanel()
    with pytest.raises(ServiceError) as error:
        await _service(db_session, panel).create(_input("month"))
    assert error.value.code == "plan_squads_unknown"


async def test_created_plan_is_visible(db_session: AsyncSession) -> None:
    panel = FakePanel()
    panel.add_squad(SQUAD, "Европа")
    service = _service(db_session, panel)

    created = await service.create(_input("month"))

    assert created.id > 0
    assert [plan.code for plan in await service.visible()] == ["month"]


async def test_duplicate_code_is_rejected(db_session: AsyncSession) -> None:
    panel = FakePanel()
    panel.add_squad(SQUAD, "Европа")
    service = _service(db_session, panel)
    await service.create(_input("month"))

    with pytest.raises(ServiceError) as error:
        await service.create(_input("month"))
    assert error.value.code == "plan_code_taken"


async def test_archived_plan_leaves_visible_list(db_session: AsyncSession) -> None:
    panel = FakePanel()
    panel.add_squad(SQUAD, "Европа")
    service = _service(db_session, panel)
    created = await service.create(_input("month"))

    await service.archive(created.id)

    assert await service.visible() == []
    assert [plan.code for plan in await service.all()] == ["month"]


async def test_missing_plan_reports_not_found(db_session: AsyncSession) -> None:
    panel = FakePanel()
    with pytest.raises(ServiceError) as error:
        await _service(db_session, panel).require(404)
    assert error.value.code == "plan_not_found"
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_plan_service.py -q`
Ожидание: FAIL, `ModuleNotFoundError: repibot_core.services.errors`

- [ ] **Шаг 3: Написать общий класс ошибок**

```python
# backend/core/src/repibot_core/services/errors.py
"""Ошибка сервиса: что произошло, а не как об этом сообщить по HTTP.

Код выбирает сервис, статус — слой API. Так одно и то же событие одинаково
называется в ответе REST, в боте и в логе.
"""

from __future__ import annotations


class ServiceError(Exception):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code
```

- [ ] **Шаг 4: Написать сервис тарифов**

```python
# backend/core/src/repibot_core/services/plans.py
"""Тарифы: витрина и управление."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Plan, TrafficResetStrategy
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.integrations.remnawave.squads import PanelSquads
from repibot_core.services.errors import ServiceError


@dataclass(frozen=True, slots=True)
class PlanInput:
    code: str
    name: dict[str, str]
    description: dict[str, str] | None
    duration_days: int
    price_rub: Decimal
    price_stars: int
    traffic_limit_bytes: int
    traffic_reset_strategy: TrafficResetStrategy
    hwid_device_limit: int
    internal_squad_uuids: list[str]
    is_trial: bool
    is_visible: bool
    sort_order: int


@dataclass(frozen=True, slots=True)
class PlanView:
    id: int
    code: str
    name: dict[str, str]
    description: dict[str, str] | None
    duration_days: int
    price_rub: Decimal
    price_stars: int
    traffic_limit_bytes: int
    traffic_reset_strategy: TrafficResetStrategy
    hwid_device_limit: int
    internal_squad_uuids: list[str]
    is_trial: bool
    is_active: bool
    is_visible: bool
    sort_order: int


class PlanService:
    def __init__(self, session: AsyncSession, squads: PanelSquads) -> None:
        self._session = session
        self._plans = PlanRepository(session)
        self._squads = squads

    async def visible(self) -> list[PlanView]:
        return [_view(plan) for plan in await self._plans.list_visible()]

    async def all(self) -> list[PlanView]:
        return [_view(plan) for plan in await self._plans.list_all()]

    async def require(self, plan_id: int) -> Plan:
        plan = await self._plans.get(plan_id)
        if plan is None:
            msg = "тариф не найден"
            raise ServiceError(msg, "plan_not_found")
        return plan

    async def create(self, data: PlanInput) -> PlanView:
        await self._check_squads(data.internal_squad_uuids)
        if await self._plans.get_by_code(data.code) is not None:
            msg = "тариф с таким кодом уже есть"
            raise ServiceError(msg, "plan_code_taken")

        # asdict, а не vars: dataclass со slots не имеет __dict__, и vars
        # на нём падает с TypeError.
        plan = await self._plans.create(is_active=True, **asdict(data))
        await self._session.commit()
        return _view(plan)

    async def update(self, plan_id: int, data: PlanInput) -> PlanView:
        plan = await self.require(plan_id)
        await self._check_squads(data.internal_squad_uuids)

        existing = await self._plans.get_by_code(data.code)
        if existing is not None and existing.id != plan.id:
            msg = "тариф с таким кодом уже есть"
            raise ServiceError(msg, "plan_code_taken")

        for field, value in asdict(data).items():
            setattr(plan, field, value)
        await self._session.commit()
        return _view(plan)

    async def archive(self, plan_id: int) -> None:
        plan = await self.require(plan_id)
        await self._plans.archive(plan)
        await self._session.commit()

    async def _check_squads(self, uuids: list[str]) -> None:
        """Сквады тарифа обязаны существовать в панели.

        Тариф с несуществующим сквадом продаётся, оплачивается и не даёт
        доступа: панель молча примет пустой набор. Ошибка здесь дешевле
        разбирательства с клиентом потом.
        """
        if not uuids:
            msg = "у тарифа должен быть хотя бы один сквад"
            raise ServiceError(msg, "plan_squads_unknown")

        known = {str(squad.uuid) for squad in await self._squads.list()}
        unknown = [uuid for uuid in uuids if uuid not in known]
        if unknown:
            msg = f"панель не знает сквадов: {', '.join(unknown)}"
            raise ServiceError(msg, "plan_squads_unknown")


def _view(plan: Plan) -> PlanView:
    return PlanView(
        id=plan.id,
        code=plan.code,
        name=plan.name,
        description=plan.description,
        duration_days=plan.duration_days,
        price_rub=plan.price_rub,
        price_stars=plan.price_stars,
        traffic_limit_bytes=plan.traffic_limit_bytes,
        traffic_reset_strategy=plan.traffic_reset_strategy,
        hwid_device_limit=plan.hwid_device_limit,
        internal_squad_uuids=list(plan.internal_squad_uuids),
        is_trial=plan.is_trial,
        is_active=plan.is_active,
        is_visible=plan.is_visible,
        sort_order=plan.sort_order,
    )
```

- [ ] **Шаг 5: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/core/tests/test_plan_service.py -q`
Ожидание: PASS, 5 тестов

- [ ] **Шаг 6: Коммит**

```bash
git add backend/core/src/repibot_core/services/errors.py backend/core/src/repibot_core/services/plans.py backend/core/tests/test_plan_service.py
git commit -m "feat: сервис тарифов с проверкой сквадов панели"
```

---

### Задача 9: Примирение с панелью

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/provisioning.py`
- Создать: `backend/core/src/repibot_core/services/dispatcher.py`
- Изменить: `backend/core/src/repibot_core/tasks.py`
- Тест: `backend/core/tests/test_provisioning.py`

**Интерфейсы:**
- Потребляет: `PanelUsers` (6), `FakePanel` (7), `SubscriptionRepository`, `PlanRepository` (5), `UserRepository`, `OutboxRepository`, `panel_username` и `SubscriptionState` (2).
- Отдаёт:
  - `TOPIC_PROVISION = "panel.provision"`.
  - `PanelState` — dataclass `(panel_id: int, short_uuid: str, subscription_url: str)`.
  - `ProvisioningService(session, users)`: `reconcile(user_id) -> PanelState`.
  - `build_dispatcher(session_factory, sender=None) -> OutboxDispatcher` в `services/dispatcher.py` — регистрирует и почтовые темы, и `panel.provision`.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_provisioning.py
"""Примирение панели с нашим состоянием."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import SubscriptionSource, TrafficResetStrategy, User
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.integrations.remnawave.client import RemnawaveUnavailable
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.provisioning import ProvisioningService
from repibot_core.testing.remnawave import FakePanel

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"


async def _prepare(session: AsyncSession) -> User:
    plan = await PlanRepository(session).create(
        code="month",
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("299.00"),
        price_stars=199,
        traffic_limit_bytes=1024,
        traffic_reset_strategy=TrafficResetStrategy.MONTH,
        hwid_device_limit=3,
        internal_squad_uuids=[SQUAD],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )
    user = User(email="p@example.org", referral_code="prov0001", telegram_id=99)
    session.add(user)
    await session.flush()

    now = datetime.now(UTC)
    await SubscriptionRepository(session).create(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionState.pending_provision,
        started_at=now,
        expires_at=now + timedelta(days=30),
        source=SubscriptionSource.purchase,
    )
    await session.commit()
    return user


def _service(session: AsyncSession, panel: FakePanel) -> ProvisioningService:
    return ProvisioningService(session, PanelUsers(panel.client()))


async def test_creates_user_with_our_name_and_tag(db_session: AsyncSession) -> None:
    user = await _prepare(db_session)
    panel = FakePanel()

    state = await _service(db_session, panel).reconcile(user.id)

    created = panel.users[state.panel_id]
    assert created["username"] == f"rp_{user.id}"
    assert created["tag"] == "REPIBOT"
    assert created["telegramId"] == 99
    assert created["hwidDeviceLimit"] == 3
    assert [squad["uuid"] for squad in created["activeInternalSquads"]] == [SQUAD]


async def test_saves_panel_id_and_short_uuid(db_session: AsyncSession) -> None:
    user = await _prepare(db_session)
    panel = FakePanel()

    state = await _service(db_session, panel).reconcile(user.id)
    await db_session.refresh(user)

    assert user.remnawave_id == state.panel_id
    assert user.remnawave_short_uuid == state.short_uuid


async def test_second_run_sends_no_writes(db_session: AsyncSession) -> None:
    """Идемпотентность: на сошедшихся данных изменяющих запросов нет."""
    user = await _prepare(db_session)
    panel = FakePanel()
    service = _service(db_session, panel)
    await service.reconcile(user.id)

    panel.requests.clear()
    await service.reconcile(user.id)

    assert [method for method, _ in panel.requests] == ["GET"]


async def test_lost_panel_id_is_recovered_by_username(db_session: AsyncSession) -> None:
    """Пользователь не дублируется, если мы потеряли числовой идентификатор."""
    user = await _prepare(db_session)
    panel = FakePanel()
    service = _service(db_session, panel)
    first = await service.reconcile(user.id)

    user.remnawave_id = None
    await db_session.commit()

    second = await service.reconcile(user.id)

    assert second.panel_id == first.panel_id
    assert len(panel.users) == 1


async def test_expired_subscription_disables_panel_user(db_session: AsyncSession) -> None:
    user = await _prepare(db_session)
    panel = FakePanel()
    service = _service(db_session, panel)
    state = await service.reconcile(user.id)

    subscription = await SubscriptionRepository(db_session).get_for_user(user.id)
    assert subscription is not None
    subscription.status = SubscriptionState.expired
    await db_session.commit()

    await service.reconcile(user.id)
    assert panel.users[state.panel_id]["status"] == "DISABLED"


async def test_unavailable_panel_raises(db_session: AsyncSession) -> None:
    user = await _prepare(db_session)
    panel = FakePanel()
    panel.fail_next(times=10)

    with pytest.raises(RemnawaveUnavailable):
        await _service(db_session, panel).reconcile(user.id)
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_provisioning.py -q`
Ожидание: FAIL, `ModuleNotFoundError: repibot_core.services.provisioning`

- [ ] **Шаг 3: Написать сервис примирения**

```python
# backend/core/src/repibot_core/services/provisioning.py
"""Приведение панели к нашему состоянию.

Одна функция на все случаи: выдача доступа после оплаты, активация триала,
смена тарифа, разбор очереди и крон-реконсиляция. Разные пути расходились бы
в мелочах, а расхождение здесь означает пользователя без доступа.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.domain.subscriptions import SubscriptionState, panel_username
from repibot_core.integrations.remnawave.types import (
    CreateUserBody,
    PanelUser,
    UpdateUserBody,
)
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.errors import ServiceError

logger = logging.getLogger(__name__)

TOPIC_PROVISION = "panel.provision"

# Тег отличает пользователей панели, которых ведём мы, от заведённых админом
# руками. Чужих реконсиляция не трогает.
PANEL_TAG = "REPIBOT"

# Статусы, при которых доступ в панели должен быть открыт.
_ALLOWED = (SubscriptionState.trial, SubscriptionState.active)


@dataclass(frozen=True, slots=True)
class PanelState:
    panel_id: int
    short_uuid: str
    subscription_url: str


class ProvisioningService:
    def __init__(self, session: AsyncSession, users: PanelUsers) -> None:
        self._session = session
        self._panel = users
        self._users = UserRepository(session)
        self._subscriptions = SubscriptionRepository(session)
        self._plans = PlanRepository(session)

    async def reconcile(self, user_id: int) -> PanelState:
        user = await self._users.get(user_id)
        if user is None:
            msg = "пользователь не найден"
            raise ServiceError(msg, "not_found")

        subscription = await self._subscriptions.get_for_user(user_id)
        if subscription is None:
            msg = "подписки нет, приводить панель не к чему"
            raise ServiceError(msg, "subscription_missing")

        plan = await self._plans.get(subscription.plan_id)
        if plan is None:  # pragma: no cover — тариф не удаляется физически
            msg = "тариф подписки не найден"
            raise ServiceError(msg, "plan_not_found")

        username = panel_username(user_id)
        desired: dict[str, Any] = {
            "status": "ACTIVE" if subscription.status in _ALLOWED else "DISABLED",
            "expireAt": subscription.expires_at,
            "trafficLimitBytes": plan.traffic_limit_bytes,
            "trafficLimitStrategy": plan.traffic_reset_strategy.value,
            "hwidDeviceLimit": plan.hwid_device_limit,
            "activeInternalSquads": [str(uuid) for uuid in plan.internal_squad_uuids],
        }

        existing = await self._find(user.remnawave_id, username)
        panel_user = (
            await self._create(username, user.telegram_id, user.email, desired)
            if existing is None
            else await self._update_if_needed(existing, desired)
        )

        user.remnawave_id = int(panel_user.id)
        user.remnawave_short_uuid = panel_user.shortUuid
        user.remnawave_subscription_url = panel_user.subscriptionUrl
        await self._session.commit()

        return PanelState(
            panel_id=int(panel_user.id),
            short_uuid=panel_user.shortUuid,
            subscription_url=panel_user.subscriptionUrl,
        )

    async def _find(self, panel_id: int | None, username: str) -> PanelUser | None:
        """Ищет пользователя панели, не создавая дублей.

        Числовой идентификатор мог потеряться — например, база восстановлена
        из бэкапа раньше панели. Поиск по имени возвращает того же самого
        пользователя, потому что имя выводится из нашего идентификатора.
        """
        if panel_id is not None:
            found = await self._panel.get(panel_id)
            if found is not None:
                return found
        return await self._panel.resolve(username=username)

    async def _create(
        self,
        username: str,
        telegram_id: int | None,
        email: str | None,
        desired: dict[str, Any],
    ) -> PanelUser:
        body = CreateUserBody(
            username=username,
            tag=PANEL_TAG,
            telegramId=telegram_id,
            email=email,
            **desired,
        )
        return await self._panel.create(body)

    async def _update_if_needed(
        self, existing: PanelUser, desired: dict[str, Any]
    ) -> PanelUser:
        """Пишет в панель только при расхождении.

        Пустой PATCH стоит нам запроса, а панели — записи в журнал изменений
        и события вебхука, на которое мы же и отреагируем.
        """
        if existing.tag != PANEL_TAG:
            logger.warning(
                "пользователь панели заведён мимо нас, правка пропущена",
                extra={"panel_user_id": existing.id, "tag": existing.tag},
            )
            return existing

        current = {
            "status": existing.status.value,
            # До секунды: панель хранит дату с миллисекундами, у нас в базе
            # микросекунды. Сравнение как есть расходилось бы всегда, и
            # реконсиляция писала бы в панель на каждом прогоне.
            "expireAt": existing.expireAt.replace(microsecond=0),
            "trafficLimitBytes": float(existing.trafficLimitBytes),
            "trafficLimitStrategy": existing.trafficLimitStrategy.value,
            "hwidDeviceLimit": existing.hwidDeviceLimit,
            "activeInternalSquads": sorted(
                str(squad.uuid) for squad in existing.activeInternalSquads
            ),
        }
        wanted = dict(desired)
        wanted["expireAt"] = desired["expireAt"].replace(microsecond=0)
        wanted["trafficLimitBytes"] = float(desired["trafficLimitBytes"])
        wanted["activeInternalSquads"] = sorted(desired["activeInternalSquads"])

        if current == wanted:
            return existing

        return await self._panel.update(UpdateUserBody(id=int(existing.id), **desired))


def build_provision_handler(
    session_factory: async_sessionmaker[AsyncSession], users: PanelUsers
) -> Any:
    """Обработчик темы panel.provision для очереди надёжной доставки.

    Своя сессия, а не сессия диспетчера: разбор очереди коммитит собственную
    транзакцию, и вмешиваться в неё выдачей доступа нельзя.
    """

    async def handle(payload: dict[str, Any]) -> None:
        async with session_factory() as session:
            await ProvisioningService(session, users).reconcile(int(payload["user_id"]))

    return handle
```

- [ ] **Шаг 4: Собрать общий диспетчер очереди**

```python
# backend/core/src/repibot_core/services/dispatcher.py
"""Сборка диспетчера очереди со всеми известными темами.

Отдельный модуль, потому что тем стало больше одной группы: почта не должна
знать про панель, а панель — про почту.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repibot_core.integrations.email.sender import EmailSender
from repibot_core.integrations.remnawave.client import create_remnawave_client
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.email_dispatch import build_dispatcher as build_email_dispatcher
from repibot_core.services.outbox import OutboxDispatcher
from repibot_core.services.provisioning import TOPIC_PROVISION, build_provision_handler


def build_dispatcher(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    sender: EmailSender | None = None,
    users: PanelUsers | None = None,
) -> OutboxDispatcher:
    dispatcher = build_email_dispatcher(sender)
    panel = users if users is not None else PanelUsers(create_remnawave_client())
    dispatcher.register(TOPIC_PROVISION, build_provision_handler(session_factory, panel))
    return dispatcher
```

В `tasks.py` заменить `_dispatcher()` на вызов нового сборщика: тело `process_outbox` создаёт `factory`, её же и передаёт.

```python
        factory = create_session_factory(engine)
        async with factory() as session:
            delivered = await _dispatcher(factory).process(session)
```

```python
def _dispatcher(factory: async_sessionmaker[AsyncSession]) -> OutboxDispatcher:
    """Собирается на каждый прогон.

    Импорт внутри функции разрывает цикл: services импортирует эту же задачу,
    чтобы поставить её после коммита.
    """
    from repibot_core.services.dispatcher import build_dispatcher

    return build_dispatcher(factory)
```

- [ ] **Шаг 5: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/core/tests/test_provisioning.py -q`
Ожидание: PASS, 6 тестов

- [ ] **Шаг 6: Коммит**

```bash
git add backend/core/src/repibot_core/services backend/core/src/repibot_core/tasks.py backend/core/tests/test_provisioning.py
git commit -m "feat: идемпотентное примирение панели с нашим состоянием"
```

---

### Задача 10: Админское API тарифов

**Файлы:**
- Изменить: `backend/api/src/repibot_api/routers/admin.py`
- Изменить: `backend/api/src/repibot_api/schemas.py`
- Изменить: `backend/api/src/repibot_api/errors.py`
- Тест: `backend/api/tests/test_admin_plans.py`

**Интерфейсы:**
- Потребляет: `PlanService`, `PlanInput`, `PlanView` (8), `PanelSquads` (6), `require_role` (существует).
- Отдаёт: схемы `PlanRequest`, `PlanResponse`, `SquadResponse`; функцию `api_error_from_service(error: ServiceError) -> ApiError` в `errors.py`.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/api/tests/test_admin_plans.py
"""Тарифы через админское API."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"

PLAN_BODY = {
    "code": "month",
    "name": {"ru": "Месяц", "en": "Month"},
    "description": None,
    "duration_days": 30,
    "price_rub": "299.00",
    "price_stars": 199,
    "traffic_limit_bytes": 0,
    "traffic_reset_strategy": "NO_RESET",
    "hwid_device_limit": 3,
    "internal_squad_uuids": [SQUAD],
    "is_trial": False,
    "is_visible": True,
    "sort_order": 0,
}


async def test_support_cannot_touch_plans(
    api_client: AsyncClient, support_headers: dict[str, str]
) -> None:
    """Роль support к тарифам доступа не имеет — это правило архитектуры."""
    response = await api_client.get("/api/admin/plans", headers=support_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_admin_creates_and_archives_plan(
    api_client: AsyncClient, admin_headers: dict[str, str], fake_panel_squad: None
) -> None:
    created = await api_client.post("/api/admin/plans", json=PLAN_BODY, headers=admin_headers)
    assert created.status_code == 201
    plan_id = created.json()["id"]

    listed = await api_client.get("/api/admin/plans", headers=admin_headers)
    assert [plan["code"] for plan in listed.json()] == ["month"]

    archived = await api_client.delete(f"/api/admin/plans/{plan_id}", headers=admin_headers)
    assert archived.status_code == 204

    visible = await api_client.get("/api/plans")
    assert visible.json() == []


async def test_unknown_squad_is_rejected(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await api_client.post("/api/admin/plans", json=PLAN_BODY, headers=admin_headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "plan_squads_unknown"


async def test_squads_come_from_panel(
    api_client: AsyncClient, admin_headers: dict[str, str], fake_panel_squad: None
) -> None:
    response = await api_client.get("/api/admin/remnawave/squads", headers=admin_headers)
    assert response.json() == [{"uuid": SQUAD, "name": "Европа"}]
```

Фикстуры `admin_headers`, `support_headers` и `fake_panel_squad` добавляются в корневой `conftest.py`: первые две выпускают access-токен пользователю с нужной ролью тем же способом, что уже используют тесты админских маршрутов подпроекта 1; третья подменяет зависимость панели заглушкой `FakePanel` с одним добавленным сквадом.

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/api/tests/test_admin_plans.py -q`
Ожидание: FAIL, 404 на `/api/admin/plans`

- [ ] **Шаг 3: Добавить схемы**

В `schemas.py`:

```python
class PlanRequest(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: dict[str, str]
    description: dict[str, str] | None = None
    duration_days: int = Field(gt=0)
    # Строкой, а не float: цена уходит в YooKassa в виде «299.00», и двоичная
    # дробь превращается в расхождение с чеком.
    price_rub: Decimal = Field(ge=0, decimal_places=2)
    price_stars: int = Field(ge=0)
    traffic_limit_bytes: int = Field(ge=0)
    traffic_reset_strategy: Literal["NO_RESET", "DAY", "WEEK", "MONTH", "MONTH_ROLLING"]
    hwid_device_limit: int = Field(ge=0)
    internal_squad_uuids: list[UUID] = Field(min_length=1)
    is_trial: bool = False
    is_visible: bool = True
    sort_order: int = 0


class PlanResponse(BaseModel):
    id: int
    code: str
    name: dict[str, str]
    description: dict[str, str] | None
    duration_days: int
    price_rub: Decimal
    price_stars: int
    traffic_limit_bytes: int
    traffic_reset_strategy: str
    hwid_device_limit: int
    internal_squad_uuids: list[UUID]
    is_trial: bool
    is_active: bool
    is_visible: bool
    sort_order: int


class SquadResponse(BaseModel):
    uuid: UUID
    name: str
```

- [ ] **Шаг 4: Научить слой ошибок кодам сервисов**

В `errors.py` рядом с `_AUTH_STATUS`:

```python
# Статус выбирается здесь, а не в сервисе: сервис знает, что произошло, а не
# как об этом принято сообщать по HTTP.
_SERVICE_STATUS = {
    "not_found": 404,
    "plan_not_found": 404,
    "plan_inactive": 409,
    "plan_code_taken": 409,
    "plan_squads_unknown": 422,
    "subscription_missing": 404,
    "subscription_exists": 409,
    "trial_already_used": 409,
    "trial_requires_telegram": 409,
    "trial_disabled": 409,
    "device_not_found": 404,
    # Не наша поломка, а недоступность панели: человеку нужно повторить
    # позже, а не искать ошибку у себя.
    "panel_unavailable": 503,
}


def api_error_from_service(error: ServiceError) -> ApiError:
    return ApiError(str(error), _SERVICE_STATUS.get(error.code, 400), error.code)
```

- [ ] **Шаг 5: Написать роутер**

В `routers/admin.py` добавить зависимость сборки сервиса и маршруты. Роутер разбирает вход, зовёт сервис и форматирует ответ — бизнес-логики в нём нет.

```python
def _plans(session: AsyncSession) -> PlanService:
    return PlanService(session, PanelSquads(create_remnawave_client()))


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> list[PlanResponse]:
    return [_plan_response(plan) for plan in await _plans(session).all()]


@router.post("/plans", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: PlanRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> PlanResponse:
    try:
        created = await _plans(session).create(_plan_input(payload))
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except RemnawaveUnavailable as error:
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error
    return _plan_response(created)
```

```python
@router.patch("/plans/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: int,
    payload: PlanRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> PlanResponse:
    try:
        updated = await _plans(session).update(plan_id, _plan_input(payload))
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except RemnawaveUnavailable as error:
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error
    return _plan_response(updated)


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_plan(
    plan_id: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> None:
    """Архивация, а не удаление: на тариф ссылаются подписки и журнал."""
    try:
        await _plans(session).archive(plan_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error


@router.get("/remnawave/squads", response_model=list[SquadResponse])
async def list_squads(
    _: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
) -> list[SquadResponse]:
    """Сквады читаются из панели, а не хранятся у нас: их состав меняет админ панели."""
    try:
        squads = await PanelSquads(create_remnawave_client()).list()
    except RemnawaveUnavailable as error:
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error
    return [SquadResponse(uuid=squad.uuid, name=squad.name) for squad in squads]


def _plan_input(payload: PlanRequest) -> PlanInput:
    return PlanInput(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        duration_days=payload.duration_days,
        price_rub=payload.price_rub,
        price_stars=payload.price_stars,
        traffic_limit_bytes=payload.traffic_limit_bytes,
        traffic_reset_strategy=TrafficResetStrategy(payload.traffic_reset_strategy),
        hwid_device_limit=payload.hwid_device_limit,
        # В базе колонка строковая: ARRAY(UUID) с as_uuid=False, и объекты UUID
        # туда не уедут.
        internal_squad_uuids=[str(uuid) for uuid in payload.internal_squad_uuids],
        is_trial=payload.is_trial,
        is_visible=payload.is_visible,
        sort_order=payload.sort_order,
    )


def _plan_response(plan: PlanView) -> PlanResponse:
    return PlanResponse(
        id=plan.id,
        code=plan.code,
        name=plan.name,
        description=plan.description,
        duration_days=plan.duration_days,
        price_rub=plan.price_rub,
        price_stars=plan.price_stars,
        traffic_limit_bytes=plan.traffic_limit_bytes,
        traffic_reset_strategy=plan.traffic_reset_strategy.value,
        hwid_device_limit=plan.hwid_device_limit,
        internal_squad_uuids=[UUID(uuid) for uuid in plan.internal_squad_uuids],
        is_trial=plan.is_trial,
        is_active=plan.is_active,
        is_visible=plan.is_visible,
        sort_order=plan.sort_order,
    )
```

- [ ] **Шаг 6: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/api/tests/test_admin_plans.py -q`
Ожидание: PASS, 4 теста

- [ ] **Шаг 7: Коммит**

```bash
git add backend/api backend/core/tests conftest.py
git commit -m "feat: админские эндпоинты тарифов и списка сквадов панели"
```

---

### Задача 11: Сервис подписок

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/subscriptions.py`
- Тест: `backend/core/tests/test_subscription_service.py`

**Интерфейсы:**
- Потребляет: домен (2), репозитории (5), `ProvisioningService` и `TOPIC_PROVISION` (9), `PlanService` (8).
- Отдаёт: `SubscriptionView` — dataclass `(plan_code, plan_name, status, started_at, expires_at, subscription_url, traffic_limit_bytes, hwid_device_limit, is_trial)`; `SubscriptionService(session, settings, provisioning)` с методами:
  - `current(user_id) -> SubscriptionView | None`
  - `trial_available(user_id) -> bool`
  - `activate_trial(user_id) -> SubscriptionView`
  - `grant_days(user_id, plan, days, *, source, event_type, actor, actor_user_id=None, comment=None) -> SubscriptionView`
  - `change_plan(user_id, plan_id, *, actor, actor_user_id) -> SubscriptionView`
  - `expire_due(now, limit=200) -> int`

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_subscription_service.py
"""Триал, начисление, смена тарифа, истечение."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    OutboxMessage,
    SubscriptionActor,
    SubscriptionEvent,
    SubscriptionEventType,
    SubscriptionSource,
    TrafficResetStrategy,
    User,
)
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.errors import ServiceError
from repibot_core.services.provisioning import TOPIC_PROVISION, ProvisioningService
from repibot_core.services.subscriptions import SubscriptionService
from repibot_core.settings import get_settings
from repibot_core.testing.remnawave import FakePanel

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"


async def _plan(session: AsyncSession, code: str, **overrides: object) -> object:
    fields: dict[str, object] = {
        "code": code,
        "name": {"ru": code, "en": code},
        "description": None,
        "duration_days": 30,
        "price_rub": Decimal("300.00"),
        "price_stars": 199,
        "traffic_limit_bytes": 0,
        "traffic_reset_strategy": TrafficResetStrategy.NO_RESET,
        "hwid_device_limit": 3,
        "internal_squad_uuids": [SQUAD],
        "is_trial": False,
        "is_active": True,
        "is_visible": True,
        "sort_order": 0,
    }
    fields.update(overrides)
    return await PlanRepository(session).create(**fields)


async def _user(session: AsyncSession, code: str, telegram_id: int | None) -> User:
    user = User(email=f"{code}@example.org", referral_code=code, telegram_id=telegram_id)
    session.add(user)
    await session.flush()
    await session.commit()
    return user


def _service(session: AsyncSession, panel: FakePanel) -> SubscriptionService:
    provisioning = ProvisioningService(session, PanelUsers(panel.client()))
    return SubscriptionService(session, get_settings(), provisioning)


async def test_trial_requires_telegram(db_session: AsyncSession) -> None:
    await _plan(db_session, "trial", is_trial=True, duration_days=3, price_rub=Decimal("0.00"))
    user = await _user(db_session, "sub00001", None)

    with pytest.raises(ServiceError) as error:
        await _service(db_session, FakePanel()).activate_trial(user.id)
    assert error.value.code == "trial_requires_telegram"


async def test_trial_is_given_once_per_telegram(db_session: AsyncSession) -> None:
    """Правило висит на Telegram, а не на аккаунте: аккаунт легко завести заново."""
    await _plan(db_session, "trial", is_trial=True, duration_days=3, price_rub=Decimal("0.00"))
    first = await _user(db_session, "sub00002", 4242)
    service = _service(db_session, FakePanel())
    await service.activate_trial(first.id)

    second = await _user(db_session, "sub00003", 4242)
    with pytest.raises(ServiceError) as error:
        await service.activate_trial(second.id)
    assert error.value.code == "trial_already_used"


async def test_trial_without_active_plan_is_disabled(db_session: AsyncSession) -> None:
    user = await _user(db_session, "sub00004", 11)
    with pytest.raises(ServiceError) as error:
        await _service(db_session, FakePanel()).activate_trial(user.id)
    assert error.value.code == "trial_disabled"


async def test_trial_gives_link_and_writes_event(db_session: AsyncSession) -> None:
    await _plan(db_session, "trial", is_trial=True, duration_days=3, price_rub=Decimal("0.00"))
    user = await _user(db_session, "sub00005", 12)

    view = await _service(db_session, FakePanel()).activate_trial(user.id)

    assert view.status is SubscriptionState.trial
    assert view.subscription_url is not None

    events = (await db_session.execute(select(SubscriptionEvent))).scalars().all()
    assert [(event.type, event.days_delta) for event in events] == [
        (SubscriptionEventType.trial, 3)
    ]


async def test_dead_panel_leaves_pending_and_queued_task(db_session: AsyncSession) -> None:
    """Панель лежит — дни всё равно начислены, выдача уходит в очередь."""
    await _plan(db_session, "trial", is_trial=True, duration_days=3, price_rub=Decimal("0.00"))
    user = await _user(db_session, "sub00006", 13)
    panel = FakePanel()
    panel.fail_next(times=10)

    view = await _service(db_session, panel).activate_trial(user.id)

    assert view.status is SubscriptionState.pending_provision
    assert view.subscription_url is None
    queued = (await db_session.execute(select(OutboxMessage))).scalars().all()
    assert [message.topic for message in queued] == [TOPIC_PROVISION]


async def test_grant_days_extends_from_expiry(db_session: AsyncSession) -> None:
    plan = await _plan(db_session, "month")
    user = await _user(db_session, "sub00007", 14)
    service = _service(db_session, FakePanel())

    first = await service.grant_days(
        user.id,
        plan,
        30,
        source=SubscriptionSource.purchase,
        event_type=SubscriptionEventType.purchase,
        actor=SubscriptionActor.system,
    )
    second = await service.grant_days(
        user.id,
        plan,
        30,
        source=SubscriptionSource.purchase,
        event_type=SubscriptionEventType.renew,
        actor=SubscriptionActor.system,
    )

    assert (second.expires_at - first.expires_at) == timedelta(days=30)


async def test_change_plan_converts_remainder(db_session: AsyncSession) -> None:
    cheap = await _plan(db_session, "cheap", price_rub=Decimal("300.00"))
    pricey = await _plan(db_session, "pricey", price_rub=Decimal("600.00"))
    user = await _user(db_session, "sub00008", 15)
    service = _service(db_session, FakePanel())
    await service.grant_days(
        user.id,
        cheap,
        30,
        source=SubscriptionSource.purchase,
        event_type=SubscriptionEventType.purchase,
        actor=SubscriptionActor.system,
    )

    changed = await service.change_plan(
        user.id, pricey.id, actor=SubscriptionActor.admin, actor_user_id=user.id
    )

    remaining = (changed.expires_at - datetime.now(UTC)).days
    assert 14 <= remaining <= 15


async def test_expire_due_marks_and_disables(db_session: AsyncSession) -> None:
    plan = await _plan(db_session, "month")
    user = await _user(db_session, "sub00009", 16)
    panel = FakePanel()
    service = _service(db_session, panel)
    await service.grant_days(
        user.id,
        plan,
        1,
        source=SubscriptionSource.purchase,
        event_type=SubscriptionEventType.purchase,
        actor=SubscriptionActor.system,
    )

    count = await service.expire_due(now=datetime.now(UTC) + timedelta(days=2))

    assert count == 1
    view = await service.current(user.id)
    assert view is not None
    assert view.status is SubscriptionState.expired
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_subscription_service.py -q`
Ожидание: FAIL, `ModuleNotFoundError: repibot_core.services.subscriptions`

- [ ] **Шаг 3: Написать сервис**

Ключевые решения, которые обязаны попасть в код:

1. **Порядок.** Изменение подписки, запись события и постановка задачи в `outbox` — одна транзакция, коммит. Только после коммита — синхронная попытка `provisioning.reconcile` с таймаутом `settings.remnawave_provision_timeout_seconds`. Неудача глушится и логируется: она уже покрыта очередью.
2. **Успешная попытка** переводит подписку из `pending_provision` в `trial` или `active` вторым коммитом и гасит сообщение очереди — повторная выдача бессмысленна.
3. **Триал**: проверка `user.telegram_id`, `TrialRepository.get`, `PlanRepository.active_trial`, отсутствие подписки. Запись в `trial_grants` идёт в той же транзакции, что и подписка: иначе двойной клик даёт два триала.
4. **Смена тарифа** при `settings.plan_change_keeps_remainder` считает остаток через `convert_remainder`; иначе срок берётся от нового тарифа. Триальный тариф остатка не даёт — `convert_remainder` на нулевой цене бросает `ValueError`, поэтому для триала остаток считается нулём без вызова.
5. **`expire_due`** идёт по `SubscriptionRepository.list_due`, ставит `expired`, пишет событие с `days_delta = 0` и ставит задачу примирения на каждого — снятие доступа делает панель, а не мы.

```python
# backend/core/src/repibot_core/services/subscriptions.py
"""Подписка: единственное место, которое двигает дату окончания."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    Plan,
    SubscriptionActor,
    SubscriptionEventType,
    SubscriptionSource,
)
from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.db.repositories.trials import TrialRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.domain.subscriptions import (
    SubscriptionState,
    convert_remainder,
    extend,
)
from repibot_core.integrations.remnawave.client import RemnawaveError
from repibot_core.services.errors import ServiceError
from repibot_core.services.provisioning import TOPIC_PROVISION, ProvisioningService
from repibot_core.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SubscriptionView:
    plan_code: str
    plan_name: dict[str, str]
    status: SubscriptionState
    started_at: datetime
    expires_at: datetime
    subscription_url: str | None
    traffic_limit_bytes: int
    hwid_device_limit: int
    is_trial: bool


class SubscriptionService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        provisioning: ProvisioningService,
    ) -> None:
        self._session = session
        self._settings = settings
        self._provisioning = provisioning
        self._users = UserRepository(session)
        self._plans = PlanRepository(session)
        self._subscriptions = SubscriptionRepository(session)
        self._trials = TrialRepository(session)
        self._outbox = OutboxRepository(session)

    async def current(self, user_id: int) -> SubscriptionView | None:
        subscription = await self._subscriptions.get_for_user(user_id)
        if subscription is None:
            return None
        plan = await self._plans.get(subscription.plan_id)
        if plan is None:  # pragma: no cover — тариф не удаляется физически
            msg = "тариф подписки не найден"
            raise ServiceError(msg, "plan_not_found")
        user = await self._users.get(user_id)
        return _view(subscription, plan, user.remnawave_subscription_url if user else None)

    async def trial_available(self, user_id: int) -> bool:
        user = await self._users.get(user_id)
        if user is None or user.telegram_id is None:
            return False
        if await self._plans.active_trial() is None:
            return False
        if await self._subscriptions.get_for_user(user_id) is not None:
            return False
        return await self._trials.get(user.telegram_id) is None

    async def grant_days(
        self,
        user_id: int,
        plan: Plan,
        days: int,
        *,
        source: SubscriptionSource,
        event_type: SubscriptionEventType,
        actor: SubscriptionActor,
        actor_user_id: int | None = None,
        comment: str | None = None,
    ) -> SubscriptionView:
        """Единственная функция, двигающая expires_at.

        В подпроекте 3 её позовёт финализация платежа; сейчас — триал и
        админское действие. Начисление, журнал и задача выдачи доступа идут
        одной транзакцией: иначе оплата может остаться без выдачи.
        """
        now = datetime.now(UTC)
        subscription = await self._subscriptions.get_for_user(user_id)
        expires_at = extend(subscription.expires_at if subscription else None, now, days)

        if subscription is None:
            subscription = await self._subscriptions.create(
                user_id=user_id,
                plan_id=plan.id,
                status=SubscriptionState.pending_provision,
                started_at=now,
                expires_at=expires_at,
                source=source,
            )
        else:
            subscription.plan_id = plan.id
            subscription.expires_at = expires_at
            subscription.status = SubscriptionState.pending_provision

        await self._subscriptions.add_event(
            user_id=user_id,
            type=event_type,
            days_delta=days,
            plan_id=plan.id,
            actor=actor,
            actor_user_id=actor_user_id,
            comment=comment,
            created_at=now,
        )
        await self._outbox.add(topic=TOPIC_PROVISION, payload={"user_id": user_id})
        await self._session.commit()

        url = await self._provision(user_id, plan)
        return _view(subscription, plan, url)

    async def change_plan(
        self,
        user_id: int,
        plan_id: int,
        *,
        actor: SubscriptionActor,
        actor_user_id: int | None = None,
    ) -> SubscriptionView:
        """Перевод на другой тариф с сохранением оплаченного остатка."""
        subscription = await self._subscriptions.get_for_user(user_id)
        if subscription is None:
            msg = "подписки нет"
            raise ServiceError(msg, "subscription_missing")

        new_plan = await self._plans.get(plan_id)
        if new_plan is None:
            msg = "тариф не найден"
            raise ServiceError(msg, "plan_not_found")
        if not new_plan.is_active:
            msg = "тариф снят с продажи"
            raise ServiceError(msg, "plan_inactive")

        current_plan = await self._plans.get(subscription.plan_id)
        now = datetime.now(UTC)
        days = new_plan.duration_days
        if self._settings.plan_change_keeps_remainder and current_plan is not None:
            # Триал остатка не даёт: стоимость его дня — ноль, и делить нечего.
            days += (
                0
                if current_plan.price_rub <= 0
                else convert_remainder(
                    expires_at=subscription.expires_at,
                    now=now,
                    current_price_rub=current_plan.price_rub,
                    current_duration_days=current_plan.duration_days,
                    new_price_rub=new_plan.price_rub,
                    new_duration_days=new_plan.duration_days,
                )
            )
            # Остаток уже посчитан от текущей даты окончания, поэтому она
            # обнуляется: иначе оплаченное время учтётся дважды.
            subscription.expires_at = now

        return await self.grant_days(
            user_id,
            new_plan,
            days,
            source=subscription.source,
            event_type=SubscriptionEventType.plan_change,
            actor=actor,
            actor_user_id=actor_user_id,
        )

    async def expire_due(self, *, now: datetime, limit: int = 200) -> int:
        """Переводит просроченные подписки в expired и ставит снятие доступа."""
        due = await self._subscriptions.list_due(now=now, limit=limit)
        for subscription in due:
            subscription.status = SubscriptionState.expired
            await self._subscriptions.add_event(
                user_id=subscription.user_id,
                type=SubscriptionEventType.expired,
                days_delta=0,
                plan_id=subscription.plan_id,
                actor=SubscriptionActor.system,
                actor_user_id=None,
                comment="срок подписки истёк",
                created_at=now,
            )
            await self._outbox.add(
                topic=TOPIC_PROVISION, payload={"user_id": subscription.user_id}
            )
        await self._session.commit()
        return len(due)

    async def activate_trial(self, user_id: int) -> SubscriptionView:
        user = await self._users.get(user_id)
        if user is None:
            msg = "пользователь не найден"
            raise ServiceError(msg, "not_found")
        if user.telegram_id is None:
            # Почту накрутить тривиально, поэтому триал требует Telegram.
            msg = "для триала нужен привязанный Telegram"
            raise ServiceError(msg, "trial_requires_telegram")
        # Своя подписка проверяется раньше чужого триала: человеку с активной
        # подпиской честнее сказать «она у вас уже есть», а не «триал
        # выдавался» — второе он прочтёт как обвинение в накрутке.
        if await self._subscriptions.get_for_user(user_id) is not None:
            msg = "подписка уже есть"
            raise ServiceError(msg, "subscription_exists")
        if await self._trials.get(user.telegram_id) is not None:
            msg = "триал по этому Telegram уже выдавался"
            raise ServiceError(msg, "trial_already_used")

        plan = await self._plans.active_trial()
        if plan is None:
            msg = "триал не настроен"
            raise ServiceError(msg, "trial_disabled")

        await self._trials.create(telegram_id=user.telegram_id, user_id=user_id)
        return await self.grant_days(
            user_id,
            plan,
            plan.duration_days,
            source=SubscriptionSource.trial,
            event_type=SubscriptionEventType.trial,
            actor=SubscriptionActor.user,
            actor_user_id=user_id,
        )
```

```python
    async def _provision(self, user_id: int, plan: Plan) -> str | None:
        """Синхронная попытка выдачи доступа. Вызывается только после коммита.

        Отказ здесь не ошибка сценария: задача уже лежит в очереди, и воркер
        доведёт выдачу. Пользователю в этот момент показывается ожидание.

        Вне транзакции намеренно: медленная панель иначе держит блокировки
        строк, а её отказ откатывал бы уже принятое решение о начислении.
        """
        try:
            state = await asyncio.wait_for(
                self._provisioning.reconcile(user_id),
                timeout=self._settings.remnawave_provision_timeout_seconds,
            )
        except (RemnawaveError, TimeoutError, ServiceError):
            logger.info(
                "панель не ответила сразу, выдача уйдёт очередью",
                extra={"user_id": user_id},
            )
            return None

        subscription = await self._subscriptions.get_for_user(user_id)
        if subscription is not None:
            subscription.status = (
                SubscriptionState.trial if plan.is_trial else SubscriptionState.active
            )
            await self._session.commit()
        return state.subscription_url


def _view(subscription: Subscription, plan: Plan, url: str | None) -> SubscriptionView:
    return SubscriptionView(
        plan_code=plan.code,
        plan_name=plan.name,
        status=subscription.status,
        started_at=subscription.started_at,
        expires_at=subscription.expires_at,
        subscription_url=url,
        traffic_limit_bytes=plan.traffic_limit_bytes,
        hwid_device_limit=plan.hwid_device_limit,
        is_trial=plan.is_trial,
    )


```

`Subscription` добавить в импорты моделей. Ссылка подписки не собирается из
адреса панели: её публичный домен настраивается в панели отдельно и с
`REMNAWAVE_BASE_URL` не обязан совпадать. Значение приходит из ответа панели и
лежит в `users.remnawave_subscription_url`, обновляясь на каждом примирении —
`revoke` в панели меняет `shortUuid`, и собранная однажды ссылка начала бы
вести в никуда. Метод `current` читает поле пользователя.

- [ ] **Шаг 4: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/core/tests/test_subscription_service.py -q`
Ожидание: PASS, 8 тестов

- [ ] **Шаг 5: Коммит**

```bash
git add backend/core/src/repibot_core/services/subscriptions.py backend/core/tests/test_subscription_service.py
git commit -m "feat: триал, начисление дней и смена тарифа"
```

---

### Задача 12: Клиентское API подписки

**Файлы:**
- Создать: `backend/api/src/repibot_api/routers/subscription.py`
- Изменить: `backend/api/src/repibot_api/main.py`
- Изменить: `backend/api/src/repibot_api/schemas.py`
- Тест: `backend/api/tests/test_subscription_api.py`

**Интерфейсы:**
- Потребляет: `SubscriptionService`, `PlanService`, `api_error_from_service`.
- Отдаёт: маршруты `GET /api/plans`, `GET /api/me/subscription`, `POST /api/me/subscription/trial`; схемы `PublicPlanResponse`, `SubscriptionResponse`.

Роутер отдельным файлом, а не дописыванием в `me.py`: в подпроекте 1 общий файл дважды становился местом столкновения параллельных задач.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/api/tests/test_subscription_api.py
"""Витрина и подписка глазами клиента."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.docker


async def test_plans_are_public(api_client: AsyncClient, month_plan: int) -> None:
    """Витрина видна до входа: иначе не на что смотреть до регистрации."""
    response = await api_client.get("/api/plans")
    assert response.status_code == 200
    assert [plan["code"] for plan in response.json()] == ["month"]


async def test_subscription_is_null_for_newcomer(
    api_client: AsyncClient, user_headers: dict[str, str], trial_plan: int
) -> None:
    """Отсутствие подписки — не ошибка. Иначе фронтенд не отличит её от отказа."""
    response = await api_client.get("/api/me/subscription", headers=user_headers)
    assert response.status_code == 200
    assert response.json() == {"subscription": None, "trial_available": True}


async def test_trial_activation_returns_link(
    api_client: AsyncClient, telegram_user_headers: dict[str, str], trial_plan: int
) -> None:
    response = await api_client.post(
        "/api/me/subscription/trial", headers=telegram_user_headers
    )
    assert response.status_code == 201
    body = response.json()["subscription"]
    assert body["status"] == "trial"
    assert body["subscription_url"].startswith("https://")


async def test_second_trial_is_conflict(
    api_client: AsyncClient, telegram_user_headers: dict[str, str], trial_plan: int
) -> None:
    await api_client.post("/api/me/subscription/trial", headers=telegram_user_headers)
    response = await api_client.post(
        "/api/me/subscription/trial", headers=telegram_user_headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "subscription_exists"


async def test_trial_without_telegram_is_conflict(
    api_client: AsyncClient, user_headers: dict[str, str], trial_plan: int
) -> None:
    response = await api_client.post("/api/me/subscription/trial", headers=user_headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "trial_requires_telegram"


async def test_anonymous_cannot_activate_trial(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/me/subscription/trial")
    assert response.status_code == 401
```

Фикстуры `month_plan`, `trial_plan`, `user_headers`, `telegram_user_headers` добавляются в корневой `conftest.py`: тарифы создаются напрямую через `PlanRepository`, заголовки — тем же способом, что и в тестах подпроекта 1.

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/api/tests/test_subscription_api.py -q`
Ожидание: FAIL, 404 на `/api/plans`

- [ ] **Шаг 3: Добавить схемы ответов**

```python
class PublicPlanResponse(BaseModel):
    """Тариф в витрине. Внутренние поля наружу не уезжают.

    internal_squad_uuids не отдаётся: состав локаций — наша кухня, а не то,
    что клиент должен видеть в ответе API.
    """

    id: int
    code: str
    name: dict[str, str]
    description: dict[str, str] | None
    duration_days: int
    price_rub: Decimal
    price_stars: int
    traffic_limit_bytes: int
    hwid_device_limit: int
    is_trial: bool


class SubscriptionResponse(BaseModel):
    plan_code: str
    plan_name: dict[str, str]
    status: str
    started_at: datetime
    expires_at: datetime
    subscription_url: str | None
    traffic_limit_bytes: int
    hwid_device_limit: int


class SubscriptionStateResponse(BaseModel):
    subscription: SubscriptionResponse | None
    trial_available: bool
```

- [ ] **Шаг 4: Написать роутер и подключить его**

```python
# backend/api/src/repibot_api/routers/subscription.py
"""Витрина тарифов и подписка текущего пользователя."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import AuthContext, current_context, db_session
from repibot_api.errors import ApiError, api_error_from_service
from repibot_api.schemas import (
    PublicPlanResponse,
    SubscriptionResponse,
    SubscriptionStateResponse,
)
from repibot_core.integrations.remnawave.client import (
    RemnawaveUnavailable,
    create_remnawave_client,
)
from repibot_core.integrations.remnawave.squads import PanelSquads
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.errors import ServiceError
from repibot_core.services.plans import PlanService
from repibot_core.services.provisioning import ProvisioningService
from repibot_core.services.subscriptions import SubscriptionService, SubscriptionView
from repibot_core.settings import get_settings

router = APIRouter(tags=["subscription"])


def _subscriptions(session: AsyncSession) -> SubscriptionService:
    client = create_remnawave_client()
    return SubscriptionService(
        session, get_settings(), ProvisioningService(session, PanelUsers(client))
    )


@router.get("/api/plans", response_model=list[PublicPlanResponse])
async def list_plans(
    session: Annotated[AsyncSession, Depends(db_session)],
) -> list[PublicPlanResponse]:
    """Витрина открыта без входа: до регистрации человеку не на что смотреть."""
    service = PlanService(session, PanelSquads(create_remnawave_client()))
    return [
        PublicPlanResponse(
            id=plan.id,
            code=plan.code,
            name=plan.name,
            description=plan.description,
            duration_days=plan.duration_days,
            price_rub=plan.price_rub,
            price_stars=plan.price_stars,
            traffic_limit_bytes=plan.traffic_limit_bytes,
            hwid_device_limit=plan.hwid_device_limit,
            is_trial=plan.is_trial,
        )
        for plan in await service.visible()
    ]


@router.get("/api/me/subscription", response_model=SubscriptionStateResponse)
async def my_subscription(
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(current_context)],
) -> SubscriptionStateResponse:
    service = _subscriptions(session)
    view = await service.current(context.principal.user_id)
    return SubscriptionStateResponse(
        subscription=_response(view) if view is not None else None,
        trial_available=await service.trial_available(context.principal.user_id),
    )


@router.post(
    "/api/me/subscription/trial",
    response_model=SubscriptionStateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def activate_trial(
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(current_context)],
) -> SubscriptionStateResponse:
    try:
        view = await _subscriptions(session).activate_trial(context.principal.user_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except RemnawaveUnavailable as error:  # pragma: no cover — выдача уходит в очередь
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error
    return SubscriptionStateResponse(subscription=_response(view), trial_available=False)


def _response(view: SubscriptionView) -> SubscriptionResponse:
    return SubscriptionResponse(
        plan_code=view.plan_code,
        plan_name=view.plan_name,
        status=view.status.value,
        started_at=view.started_at,
        expires_at=view.expires_at,
        subscription_url=view.subscription_url,
        traffic_limit_bytes=view.traffic_limit_bytes,
        hwid_device_limit=view.hwid_device_limit,
    )
```

В `main.py` подключить роутер рядом с остальными: `app.include_router(subscription.router)`.

- [ ] **Шаг 5: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/api/tests/test_subscription_api.py -q`
Ожидание: PASS, 6 тестов

- [ ] **Шаг 6: Коммит**

```bash
git add backend/api conftest.py
git commit -m "feat: витрина тарифов и подписка в клиентском API"
```

---

### Задача 13: Крон истечения

**Файлы:**
- Изменить: `backend/core/src/repibot_core/tasks.py`
- Тест: `backend/worker/tests/test_expire_task.py`

**Интерфейсы:**
- Потребляет: `SubscriptionService.expire_due` (11).
- Отдаёт: задачу `expire_subscriptions()` с расписанием `0 * * * *`, возвращающую `{"expired": <число>}`.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/worker/tests/test_expire_task.py
"""Крон истечения снимает доступ у просроченных подписок."""

from __future__ import annotations

import pytest

from repibot_core.tasks import expire_subscriptions

pytestmark = pytest.mark.docker


def test_task_is_scheduled_hourly() -> None:
    """Раз в час, а не раз в сутки: сутки лишнего доступа — это деньги."""
    assert expire_subscriptions.labels["schedule"] == [{"cron": "0 * * * *"}]


async def test_task_expires_overdue_subscription(
    postgres_url: str, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Задача ходит в базу сама, поэтому ей подменяется адрес подключения."""
    plan = await PlanRepository(db_session).create(
        code="month",
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("299.00"),
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=3,
        internal_squad_uuids=["11111111-1111-4111-8111-111111111111"],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )
    user = User(email="exp@example.org", referral_code="exp00001")
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(UTC)
    await SubscriptionRepository(db_session).create(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionState.active,
        started_at=now - timedelta(days=31),
        expires_at=now - timedelta(hours=1),
        source=SubscriptionSource.purchase,
    )
    await db_session.commit()

    settings = get_settings()
    monkeypatch.setattr(settings, "database_url", postgres_url)

    assert await expire_subscriptions() == {"expired": 1}

    subscription = await SubscriptionRepository(db_session).get_for_user(user.id)
    assert subscription is not None
    await db_session.refresh(subscription)
    assert subscription.status is SubscriptionState.expired
```

Импорты теста: `Decimal`, `datetime`, `timedelta`, `UTC`, `AsyncSession`, `PlanRepository`, `SubscriptionRepository`, `TrafficResetStrategy`, `SubscriptionSource`, `User`, `SubscriptionState`, `get_settings`.

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/worker/tests/test_expire_task.py -q`
Ожидание: FAIL, `ImportError: cannot import name 'expire_subscriptions'`

- [ ] **Шаг 3: Добавить задачу**

```python
@broker.task(schedule=[{"cron": "0 * * * *"}])
async def expire_subscriptions() -> dict[str, int]:
    """Переводит просроченные подписки в expired и снимает доступ в панели.

    Раз в час, а не раз в сутки: каждый лишний час доступа после окончания
    оплаченного срока — это доступ, за который никто не заплатил. Дата
    окончания при этом не двигается: expired — следствие даты, а не решение.
    """
    engine = create_engine(get_settings().database_url)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            expired = await _subscriptions(session).expire_due(now=datetime.now(UTC))
    finally:
        await engine.dispose()

    return {"expired": expired}
```

Вспомогательная `_subscriptions(session)` собирает сервис так же, как роутер задачи 12, с импортами внутри функции — цикл `services → tasks → services` иначе не разрывается.

- [ ] **Шаг 4: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/worker/tests/test_expire_task.py -q`
Ожидание: PASS

- [ ] **Шаг 5: Коммит**

```bash
git add backend/core/src/repibot_core/tasks.py backend/worker/tests/test_expire_task.py
git commit -m "feat: ежечасное истечение подписок"
```

---

### Задача 14: Админское начисление дней

**Файлы:**
- Изменить: `backend/api/src/repibot_api/routers/admin.py`
- Изменить: `backend/api/src/repibot_api/schemas.py`
- Тест: `backend/api/tests/test_admin_subscription.py`

**Интерфейсы:**
- Потребляет: `SubscriptionService.grant_days` и `change_plan` (11), `PlanService.require` (8), `AuditLog` (существует).
- Отдаёт: маршрут `POST /api/admin/users/{user_id}/subscription`; схему `AdminSubscriptionRequest` с полями `plan_id: int`, `days: int | None`, `comment: str | None`.

Тело без `days` означает смену тарифа с конвертацией остатка, тело с `days` — начисление указанного числа дней по этому тарифу.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/api/tests/test_admin_subscription.py
"""Начисление дней и смена тарифа руками админа."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import AuditLog

pytestmark = pytest.mark.docker


async def test_admin_grants_days(
    api_client: AsyncClient,
    admin_headers: dict[str, str],
    month_plan: int,
    plain_user_id: int,
) -> None:
    response = await api_client.post(
        f"/api/admin/users/{plain_user_id}/subscription",
        json={"plan_id": month_plan, "days": 10, "comment": "компенсация"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["subscription"]["plan_code"] == "month"


async def test_grant_is_written_to_audit_log(
    api_client: AsyncClient,
    admin_headers: dict[str, str],
    month_plan: int,
    plain_user_id: int,
    db_session: AsyncSession,
) -> None:
    """Каждое действие персонала оставляет след — это правило архитектуры."""
    await api_client.post(
        f"/api/admin/users/{plain_user_id}/subscription",
        json={"plan_id": month_plan, "days": 10},
        headers=admin_headers,
    )
    records = (await db_session.execute(select(AuditLog))).scalars().all()
    assert [record.action for record in records] == ["subscription.grant"]


async def test_support_cannot_grant(
    api_client: AsyncClient,
    support_headers: dict[str, str],
    month_plan: int,
    plain_user_id: int,
) -> None:
    response = await api_client.post(
        f"/api/admin/users/{plain_user_id}/subscription",
        json={"plan_id": month_plan, "days": 10},
        headers=support_headers,
    )
    assert response.status_code == 403


async def test_unknown_plan_is_not_found(
    api_client: AsyncClient, admin_headers: dict[str, str], plain_user_id: int
) -> None:
    response = await api_client.post(
        f"/api/admin/users/{plain_user_id}/subscription",
        json={"plan_id": 404, "days": 10},
        headers=admin_headers,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "plan_not_found"
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/api/tests/test_admin_subscription.py -q`
Ожидание: FAIL, 404 на маршруте

- [ ] **Шаг 3: Написать маршрут**

Схема запроса в `schemas.py`:

```python
class AdminSubscriptionRequest(BaseModel):
    plan_id: int
    # Пустое значение означает смену тарифа с конвертацией остатка, а не
    # начисление нуля дней: у этих двух действий разный смысл.
    days: int | None = Field(default=None, gt=0)
    comment: str | None = Field(default=None, max_length=512)
```

Маршрут в `routers/admin.py`:

```python
@router.post("/users/{user_id}/subscription", response_model=SubscriptionStateResponse)
async def grant_subscription(
    user_id: int,
    payload: AdminSubscriptionRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: Annotated[AuthContext, Depends(require_role(UserRole.admin))],
    ip: Annotated[str | None, Depends(client_ip)],
) -> SubscriptionStateResponse:
    service = _subscription_service(session)
    plans = _plans(session)

    before = await service.current(user_id)
    try:
        plan = await plans.require(payload.plan_id)
        if payload.days is None:
            view = await service.change_plan(
                user_id,
                payload.plan_id,
                actor=SubscriptionActor.admin,
                actor_user_id=context.principal.user_id,
            )
        else:
            view = await service.grant_days(
                user_id,
                plan,
                payload.days,
                source=SubscriptionSource.admin,
                event_type=SubscriptionEventType.admin_grant,
                actor=SubscriptionActor.admin,
                actor_user_id=context.principal.user_id,
                comment=payload.comment,
            )
    except ServiceError as error:
        raise api_error_from_service(error) from error

    # Каждое действие персонала оставляет след с состоянием до и после:
    # спор «кому и сколько начислили» иначе не разобрать.
    await AuditRepository(session).add(
        actor_id=context.principal.user_id,
        action="subscription.grant",
        entity="subscription",
        entity_id=str(user_id),
        before=_audit_snapshot(before),
        after=_audit_snapshot(view),
        ip=ip,
    )
    await session.commit()

    return SubscriptionStateResponse(subscription=_response(view), trial_available=False)


def _audit_snapshot(view: SubscriptionView | None) -> dict[str, str] | None:
    if view is None:
        return None
    return {"plan_code": view.plan_code, "expires_at": view.expires_at.isoformat()}
```

Функции `_response` и `_subscription_service` — те же, что в задаче 12. Вынести их в `repibot_api/subscription_view.py` и импортировать в оба роутера: формирование ответа не должно быть написано дважды. Сигнатура `AuditRepository.add` — та, что уже используется в подпроекте 1; если она отличается от приведённой, брать существующую, а не менять репозиторий.

- [ ] **Шаг 4: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/api/tests/test_admin_subscription.py -q`
Ожидание: PASS, 4 теста

- [ ] **Шаг 5: Коммит**

```bash
git add backend/api
git commit -m "feat: админское начисление дней и смена тарифа"
```

---

### Задача 15: Типы API для фронтенда

**Файлы:**
- Изменить (перегенерацией): `frontend/packages/core/src/api/openapi.json`
- Изменить (перегенерацией): `frontend/packages/core/src/api/schema.d.ts`

Выполняется после того, как все эндпоинты этапа на месте: иначе типы придётся пересобирать после каждой задачи, и параллельные исполнители будут драться за один файл.

- [ ] **Шаг 1: Перегенерировать схему и типы**

```bash
uv run export-openapi
pnpm --filter @repibot/core gen:api
```

- [ ] **Шаг 2: Проверить, что генерация сошлась**

Запуск: `uv run verify-generated`
Ожидание: «Сгенерированные файлы актуальны».

- [ ] **Шаг 3: Проверить типизацию фронтенда**

Запуск: `cd frontend && pnpm typecheck`
Ожидание: без ошибок.

- [ ] **Шаг 4: Коммит**

```bash
git add frontend/packages/core/src/api
git commit -m "chore: типы API после эндпоинтов подписок"
```

---

### Задача 16: Документация этапа и проверка на живой панели

**Файлы:**
- Изменить: `docs/superpowers/plans/2026-08-06-subscriptions-core.md` (раздел «Состояние выполнения»)
- Изменить: `docs/deployment.md`
- Изменить: `README.md`

- [ ] **Шаг 1: Прогнать полную проверку**

Запуск: `uv run check`
Ожидание: все восемь проверок зелёные.

- [ ] **Шаг 2: Проверить сценарий на живой панели**

Против настоящей Remnawave 3.2.1, не против заглушки. По шагам:

1. `GET /api/admin/remnawave/squads` возвращает реальные сквады развёртывания.
2. Создать тариф на одном из них через `POST /api/admin/plans`.
3. Создать триальный тариф и активировать триал пользователем с привязанным Telegram.
4. Открыть полученный `subscription_url` — страница подписки панели отдаёт конфигурацию.
5. Подключиться клиентом (mihomo или любой другой) и убедиться, что трафик идёт.
6. Убедиться в панели, что пользователь называется `rp_<base36>`, помечен тегом `REPIBOT`, имеет ожидаемые дату окончания, лимит устройств и состав сквадов.
7. Остановить панель и повторить активацию триала другим пользователем: ответ приходит со статусом `pending_provision`, после подъёма панели воркер доводит выдачу.

Расхождения записать в раздел «Состояние выполнения» — заглушка повторяет форму ответов, но не поведение живой панели, и найденное здесь дороже всего остального в этапе.

- [ ] **Шаг 3: Дописать документацию**

В `docs/deployment.md` — раздел о первом запуске: как завести первый тариф через админское API и что для этого нужен пользователь с ролью `admin`. В `README.md` — упоминание, что подпроект 2a выполнен и что умеет система.

В разделе «Состояние выполнения» этого плана — таблица волн с отметками и список правок, найденных при сборке, по образцу плана 1b.

- [ ] **Шаг 4: Коммит**

```bash
git add docs README.md
git commit -m "docs: результаты этапа подписок и проверка на живой панели"
```

---

## Что остаётся этапу 2b

- Устройства: `GET /api/me/devices`, `POST /api/me/devices/unlink`, кэш и ограничение частоты.
- Трафик: `GET /api/me/traffic`, кэш на 60 секунд.
- Вебхуки панели: `POST /webhook/remnawave`, проверка HMAC, таблица `webhook_events`, идемпотентная обработка.
- Реконсиляция: крон, таблица `reconciliation_findings`, пропуск чужого тега.
- Интерфейсы: `/plans` и `/account/subscription` в вебе, экраны «Подписка» и «Устройства» в MiniApp, словари, состояние `pending_provision`.
- Сквозной сценарий Playwright: регистрация, привязка Telegram, триал, ссылка подписки, отвязка устройства.
