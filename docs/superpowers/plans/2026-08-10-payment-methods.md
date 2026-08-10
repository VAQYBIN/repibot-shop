# Сохранённая карта и автоплатёж Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Карта запоминается галочкой пользователя на форме YooKassa и сразу
включает автоплатёж; пользователь видит её название, может отвязать и — если
магазину подключена привязка на нулевую сумму — привязать другую.

**Architecture:** Действующая карта пользователя — отдельная строка
`saved_payment_methods`, единственная непогашенная на пользователя. Она
появляется только из проверенного ответа провайдера с `payment_method.saved:
true`, будь то обычная оплата или привязка на нулевую сумму. Привязка живёт
своей сущностью `card_bindings` и не притворяется заказом: у неё нет тарифа,
суммы и срока. Планировщик автопродления берёт метод из этой таблицы, а не
перебирает исторические payload попыток.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 async/PostgreSQL, Alembic,
httpx, TaskIQ/Valkey, React 19, Next.js 16, TanStack Query v5, TanStack Router,
Vitest.

## Global Constraints

- Доказательство привязки — только `payment_method.saved is True` в ответе,
  прочитанном у провайдера. Ни наш запрос, ни тело webhook доказательством не
  являются.
- Ручная покупка **не** передаёт `save_payment_method`: галочку показывает
  форма YooKassa, решение принимает плательщик. Автопродление передаёт
  `payment_method_id` и `save_payment_method=false`.
- Действующая карта у пользователя одна: частичный уникальный индекс по
  `user_id` при `revoked_at IS NULL`.
- Сохранение карты включает `auto_renew_enabled`; отвязка выключает его.
  Оплата без галочки не меняет ни карту, ни настройку.
- Привязка на нулевую сумму доступна не всем магазинам: при
  `YOOKASSA_ZERO_AMOUNT_BINDING=false` маршрут отвечает стабильной ошибкой
  `binding_unavailable`, а клиент не показывает кнопку.
- Все комментарии и докстринги на русском и объясняют «почему».
- Каждая задача: сначала падающий тест, затем минимальная реализация,
  тематический commit. Полный `uv run check` — перед сдачей.

---

### Task 1: Провайдер учится читать сохранённую карту

**Files:**
- Modify: `backend/core/src/repibot_core/integrations/yookassa/types.py`
- Modify: `backend/core/src/repibot_core/integrations/yookassa/client.py`
- Modify: `backend/core/tests/test_yookassa_client.py`
- Modify: `backend/core/src/repibot_core/testing/yookassa.py`
- Modify: `backend/core/tests/test_fake_yookassa.py`

**Interfaces:**
- Produces `YooKassaPayment.payment_method_saved: bool`,
  `YooKassaPayment.payment_method_title: str | None`,
  `YooKassaCardBinding(id, status, saved, title, confirmation_url)`,
  `YooKassaClient.create_card_binding(*, idempotence_key, return_url)`,
  `YooKassaClient.get_card_binding(binding_id)`.
- Consumes существующий `httpx.AsyncClient` клиента.

- [x] **Step 1: Падающий тест разбора ответа**

```python
async def test_saved_flag_and_title_come_from_the_provider_response() -> None:
    """Наш запрос не доказывает привязку: галочку ставит плательщик."""
    payment = client._parse_payment(
        {
            "id": "p1",
            "status": "succeeded",
            "amount": {"value": "299.00", "currency": "RUB"},
            "payment_method": {"id": "m1", "saved": True, "title": "Bank card *4444"},
        }
    )
    assert payment.payment_method_saved is True
    assert payment.payment_method_title == "Bank card *4444"
```

Добавить случай `saved` отсутствует → `False`, и тест, что
`create_payment(save_payment_method=False)` не кладёт поле в тело запроса.

- [x] **Step 2: Прогнать RED**

Run: `uv run pytest backend/core/tests/test_yookassa_client.py -q`
Expected: FAIL — полей нет.

- [x] **Step 3: Реализация**

`_parse_payment` читает `payment_method.saved` и `.title`.
`create_card_binding` шлёт `POST /payment_methods` телом
`{"type": "bank_card", "confirmation": {"type": "redirect", "return_url": ...}}`
с заголовком `Idempotence-Key`; `get_card_binding` читает
`GET /payment_methods/{id}`. Оба разбирают `id`, `status`
(`pending|active|inactive`), `saved`, `title`, `confirmation.confirmation_url`.

- [x] **Step 4: Заглушка E2E умеет то же**

`FakeYooKassa` возвращает `payment_method.saved` по запрошенному сценарию и
поддерживает `/v3/payment_methods` с теми же статусами.

- [x] **Step 5: Проверка**

Run: `uv run pytest backend/core/tests/test_yookassa_client.py backend/core/tests/test_fake_yookassa.py -q`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git commit -m "feat: клиент YooKassa читает сохранённую карту"
```

### Task 2: Хранение действующей карты

**Files:**
- Modify: `backend/core/src/repibot_core/db/models/commerce.py`
- Create: `backend/core/src/repibot_core/db/migrations/versions/0012_saved_cards.py`
- Create: `backend/core/src/repibot_core/services/payment_methods.py`
- Create: `backend/core/tests/test_payment_methods.py`
- Modify: `backend/core/src/repibot_core/db/models/__init__.py`
- Modify: `backend/core/tests/test_migrations.py`

**Interfaces:**
- Produces `SavedPaymentMethod`, `CardBinding`, `CardBindingStatus`,
  `PaymentMethodService.current(user_id) -> SavedCardView | None`,
  `PaymentMethodService.save(user_id, *, provider_method_id, title) -> SavedPaymentMethod`,
  `PaymentMethodService.revoke(user_id) -> bool`.
- `SavedCardView(title, linked_at)`.

- [x] **Step 1: Падающий тест**

```python
async def test_saving_a_card_replaces_the_previous_one(db_session) -> None:
    """Карта у пользователя одна: иначе продление спишет с забытой."""
    methods = PaymentMethodService(db_session)
    await methods.save(user.id, provider_method_id="m1", title="Bank card *1111")
    await methods.save(user.id, provider_method_id="m2", title="Bank card *4444")

    assert (await methods.current(user.id)).title == "Bank card *4444"
    assert await active_row_count(user.id) == 1
```

Плюс: `revoke` гасит строку и возвращает `False` при повторе; одновременное
сохранение двух карт не нарушает частичный уникальный индекс.

- [x] **Step 2: RED**

Run: `uv run pytest backend/core/tests/test_payment_methods.py -q`

- [x] **Step 3: Модели и миграция**

```python
class SavedPaymentMethod(Base):
    __tablename__ = "saved_payment_methods"
    # user_id, provider, provider_method_id, title, created_at, revoked_at
    # Index("uq_saved_methods_active", "user_id",
    #       unique=True, postgresql_where=text("revoked_at IS NULL"))

class CardBinding(Base):
    __tablename__ = "card_bindings"
    # user_id, provider_binding_id (unique), status, verified_at, created_at
```

Миграция создаёт обе таблицы и частичный индекс.

- [x] **Step 4: Сервис**

`save` в одной транзакции гасит прежнюю строку и вставляет новую; `revoke`
проставляет `revoked_at` только непогашенной строке. Ни commit, ни сеть.

- [x] **Step 5: Проверка**

Run: `uv run pytest backend/core/tests/test_payment_methods.py backend/core/tests/test_migrations.py -q`

- [x] **Step 6: Commit**

```bash
git commit -m "feat: хранение действующей карты пользователя"
```

### Task 3: Оплата запоминает карту и включает автоплатёж

**Files:**
- Modify: `backend/core/src/repibot_core/services/payments.py`
- Modify: `backend/core/src/repibot_core/services/payment_notifications.py`
- Modify: `backend/core/tests/test_payment_finalization.py`
- Modify: `backend/core/tests/test_auto_renew.py`
- Modify: `backend/api/src/repibot_api/routers/subscription.py`
- Modify: `backend/api/src/repibot_api/schemas.py`

**Interfaces:**
- Consumes `PaymentMethodService`, `YooKassaPayment.payment_method_saved`.
- `_record_yookassa_verification` дополнительно кладёт в `verified_payload`
  `payment_method_saved` и `payment_method_title`.
- `AutoRenewalService._saved_method` читает `saved_payment_methods`.
- `CreateOrderRequest.save_payment_method` удаляется из схемы API.

- [x] **Step 1: Падающие тесты**

```python
async def test_checked_box_saves_the_card_and_turns_auto_renew_on(...) -> None:
    """Иначе автоплатёж не включился бы никогда: карты для него взяться неоткуда."""
    await finalize_with(payment_method_saved=True, title="Bank card *4444")

    assert (await methods.current(user.id)).title == "Bank card *4444"
    assert subscription.auto_renew_enabled is True

async def test_unchecked_box_keeps_the_previous_card_and_setting(...) -> None:
    ...
```

И тест, что ручной заказ не отправляет провайдеру `save_payment_method`.

- [x] **Step 2: RED**

Run: `uv run pytest backend/core/tests/test_payment_finalization.py -q`

- [x] **Step 3: Реализация**

В `finalize_success` после начисления права: если проверенный payload
сообщает `payment_method_saved`, сохранить карту и включить
`auto_renew_enabled`. Всё в той же транзакции, без сети.
`create_manual_yookassa_order` перестаёт принимать `save_payment_method`.

- [x] **Step 4: Планировщик берёт карту из таблицы**

`_saved_method` возвращает `provider_method_id` действующей строки. Прежний
перебор payload попыток удалить: он считал пригодным любой
`payment_method.id`, включая несохранённые.

- [x] **Step 5: Проверка**

Run: `uv run pytest backend/core/tests/test_payment_finalization.py backend/core/tests/test_auto_renew.py backend/api/tests/test_payments_api.py -q`

- [x] **Step 6: Commit**

```bash
git commit -m "feat: оплата с галочкой запоминает карту и включает автоплатёж"
```

### Task 4: Привязка карты без списания

**Files:**
- Modify: `backend/core/src/repibot_core/services/payment_methods.py`
- Modify: `backend/core/src/repibot_core/settings.py`
- Modify: `backend/core/src/repibot_core/tasks.py`
- Modify: `backend/api/src/repibot_api/routers/webhooks.py`
- Create: `backend/core/tests/test_card_binding.py`
- Modify: `.env.example`
- Modify: `backend/core/tests/test_settings.py`

**Interfaces:**
- Produces `CardBindingService.start(user_id, provider) -> StartedBinding(confirmation_url)`,
  `CardBindingService.settle(binding_id, provider) -> bool`.
- Настройка `yookassa_zero_amount_binding: bool = False`.

- [x] **Step 1: Падающие тесты**

```python
async def test_binding_becomes_a_card_only_after_provider_confirms_saved(...) -> None:
    """Redirect пользователя ничего не доказывает: состояние читается у провайдера."""
    started = await bindings.start(user.id, provider)
    assert await methods.current(user.id) is None

    provider.set_binding(started.binding_id, status="active", saved=True)
    assert await bindings.settle(started.binding_id, provider) is True
    assert (await methods.current(user.id)).title == "Bank card *4444"
```

Плюс: `status=inactive` карту не создаёт; повторный `settle` идемпотентен;
при выключенной настройке `start` поднимает `binding_unavailable`.

- [x] **Step 2: RED**

Run: `uv run pytest backend/core/tests/test_card_binding.py -q`

- [x] **Step 3: Реализация**

`start` создаёт строку `card_bindings` и зовёт провайдера вне транзакции.
`settle` читает состояние у провайдера, и только при `status=active` и
`saved=true` сохраняет карту через `PaymentMethodService`; повтор возвращает
`False`. Включение автоплатежа здесь такое же, как при оплате.

- [x] **Step 4: Добор потерянного подтверждения**

`reconcile_pending_payments` дочитывает незавершённые привязки, а
`/webhook/yookassa` при неизвестном `object.id` пробует его как привязку.

- [x] **Step 5: Проверка**

Run: `uv run pytest backend/core/tests/test_card_binding.py backend/worker/tests/test_tasks.py -q`

- [x] **Step 6: Commit**

```bash
git commit -m "feat: привязка карты без списания"
```

### Task 5: Клиентский API карты

**Files:**
- Modify: `backend/api/src/repibot_api/routers/subscription.py`
- Modify: `backend/api/src/repibot_api/schemas.py`
- Modify: `backend/api/src/repibot_api/errors.py`
- Create: `backend/api/tests/test_payment_method_api.py`
- Modify: `frontend/packages/core/src/api/openapi.json`
- Modify: `frontend/packages/core/src/api/schema.d.ts`

**Interfaces:**
- `GET /api/me/payment-method` → `PaymentMethodResponse(title, linked_at,
  binding_available)` либо `title: null`.
- `DELETE /api/me/payment-method` → 204, автопродление выключено.
- `POST /api/me/payment-method/bindings` → `BindingResponse(confirmation_url)`.

- [x] **Step 1: Падающие тесты маршрутов**

```python
async def test_unlinking_a_card_turns_auto_renew_off(api_client, user_headers) -> None:
    """Оставить автоплатёж без карты значит обещать списание, которого не будет."""
    response = await api_client.delete("/api/me/payment-method", headers=user_headers)

    assert response.status_code == 204
    assert (await auto_renew(api_client, user_headers)) is False
```

Плюс: чужую карту не видно и не отвязать; при выключенной настройке
`POST .../bindings` отвечает 409 `binding_unavailable`.

- [x] **Step 2: RED**

Run: `uv run pytest backend/api/tests/test_payment_method_api.py -q`

- [x] **Step 3: Реализация и экспорт схемы**

Собрать сервисы явными зависимостями; клиент провайдера открывать тем же
менеджером контекста `yookassa_client`. Затем
`uv run export-openapi; uv run verify-generated`.

- [x] **Step 4: Проверка**

Run: `uv run pytest backend/api/tests -q`

- [x] **Step 5: Commit**

```bash
git commit -m "feat: клиентский API сохранённой карты"
```

### Task 6: Карта в вебе и Mini App

**Files:**
- Create: `frontend/packages/core/src/payments/card.tsx`
- Create: `frontend/packages/core/src/payments/card.test.tsx`
- Modify: `frontend/packages/core/src/index.ts`
- Modify: `frontend/packages/core/src/i18n/ru.ts`
- Modify: `frontend/packages/core/src/i18n/en.ts`
- Modify: `frontend/apps/web/src/app/account/payments/page.tsx`
- Modify: `frontend/apps/web/src/app/account/payments/page.test.tsx`
- Modify: `frontend/apps/miniapp/src/routes/payments.tsx`
- Modify: `frontend/apps/miniapp/src/routes/payments.test.tsx`

**Interfaces:**
- Produces `usePaymentMethod()`, `useUnlinkCard()`, `useStartCardBinding()`.
- Потребляет существующие `useAutoRenew`, `useCreateOrder`.

- [x] **Step 1: Падающие тесты интерфейса**

```tsx
it('выключает переключатель автоплатежа, когда карты нет', async () => {
  renderWithProviders(<PaymentsPage />)
  expect(await screen.findByRole('switch', { name: /автоплатёж/i })).toBeDisabled()
  expect(screen.getByText(/отметьте «запомнить карту»/i)).toBeVisible()
})
```

Плюс: отвязка спрашивает подтверждение; кнопка привязки скрыта при
`binding_available: false`; название карты не выдумывается на клиенте.

- [x] **Step 2: RED**

Run: `cd frontend && pnpm --filter @repibot/web test -- payments`

- [x] **Step 3: Реализация**

Хуки в общем пакете, тексты RU/EN. Заказ больше не шлёт
`save_payment_method`. Веб открывает `confirmation_url` привязки через
`window.open(..., 'noopener,noreferrer')`, Mini App — через
`openTelegramUrl`.

- [x] **Step 4: Проверка**

Run: `cd frontend && pnpm -r test && pnpm -r --parallel typecheck && pnpm lint`

- [x] **Step 5: Commit**

```bash
git commit -m "feat: управление картой в кабинете и Mini App"
```

### Task 7: Документация и сквозной сценарий

**Files:**
- Modify: `docs/deployment.md`
- Modify: `README.md`
- Modify: `frontend/apps/web/e2e/seed.ts`
- Modify: `frontend/apps/web/e2e/money-scenarios.spec.ts`
- Modify: `docs/superpowers/plans/2026-08-10-payment-methods.md`

- [x] **Step 1: Сквозной сценарий**

Оплата с сохранением карты включает автоплатёж, отвязка выключает его,
повторная оплата без галочки ничего не меняет.

- [x] **Step 2: Документация**

Описать `YOOKASSA_ZERO_AMOUNT_BINDING`, что привязку на нулевую сумму в
боевом магазине подключает менеджер YooKassa, и что галочку сохранения
показывает форма провайдера.

- [x] **Step 3: Полная проверка**

Run: `uv run check`, затем `pnpm --filter @repibot/web e2e`.

- [x] **Step 4: Commit**

```bash
git commit -m "test: сквозной сценарий карты и документация"
```

## Plan Self-Review

- **Покрытие:** задача 1 — граница провайдера; 2 — хранение; 3 — путь оплаты
  и планировщик; 4 — привязка без списания; 5 — API; 6 — обе клиентские
  поверхности; 7 — приёмка и документация.
- **Согласованность:** единственный источник карты — проверенный ответ
  провайдера; единственный потребитель — `AutoRenewalService`; единственная
  действующая строка на пользователя обеспечена индексом, а не кодом.
- **Совместимость:** `save_payment_method` уходит из публичной схемы, поэтому
  задача 5 обязана пересобрать сгенерированные артефакты, иначе `generated`
  в `uv run check` покраснеет.
