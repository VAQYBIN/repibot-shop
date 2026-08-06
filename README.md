# Re:Pibot Shop

Магазин VPN-подписок поверх панели [Remnawave](https://remna.st) 2.8.1: Telegram-бот,
Telegram MiniApp и веб-кабинет. Открытый проект, разворачивается рядом со своей панелью.

Текущее состояние: подпроект 1 «Идентичность» завершён. Регистрация по почте с
подтверждением, вход паролем, по ключу доступа (passkey) и через Telegram (в браузере
по OpenID Connect, в MiniApp по `initData`), привязка и отвязка способов входа, профиль,
язык, список сессий и роли. Тарифов, подписок и оплат пока нет.

## Что внутри

| Каталог | Что там |
|---|---|
| `backend/core` | Бизнес-логика: домен, база, интеграции, сценарии |
| `backend/core/services/auth` | Способы входа и единственный путь выдачи сессии |
| `backend/core/integrations/telegram` | Обращения к Telegram: OpenID Connect и Bot API |
| `backend/api` | FastAPI: REST и вебхуки |
| `backend/bot` | Бот на aiogram |
| `backend/worker` | Фоновые задачи и расписание на TaskIQ |
| `frontend/apps/miniapp` | MiniApp: React 19 и Vite |
| `frontend/apps/web` | Сайт, кабинет и админка: Next.js 16 |
| `frontend/packages` | Общие пакеты: логика, компоненты, настройки инструментов |
| `docs/superpowers/specs` | Спецификации: архитектура платформы и подпроекты |
| `docs/design/logo` | Бренд-набор: знак, лок-апы, иконки. Собирается `uv run build-brand` |

## Быстрый старт

Нужны Docker, [uv](https://docs.astral.sh/uv/), Node 24 и pnpm 10.

```bash
cp .env.example .env
# заполнить BOT_TOKEN, BOT_WEBHOOK_SECRET, REMNAWAVE_TOKEN, JWT_SECRET, ENCRYPTION_KEY
docker compose up -d
curl http://localhost/health
```

Сайт откроется на `http://localhost/`, MiniApp — на `http://localhost/app/`.

## Разработка

```bash
uv sync
cd frontend && pnpm install && cd ..
uv run check
```

`uv run check` — единственная команда проверки: линтеры, типы и тесты обоих языков.
Ровно её же выполняет CI, поэтому «локально проходило» не бывает.

Локально бот удобнее запускать в режиме long polling: `BOT_USE_POLLING=true` в `.env`.

### Как получить письмо локально

Регистрация и сброс пароля работают по ссылке из письма, поэтому без почты дальше
формы не пройти. Два способа:

- **Mailpit.** `docker compose --profile dev up -d mailpit`, в `.env` поставить
  `EMAIL_SENDER=smtp`, `SMTP_HOST=mailpit`, `SMTP_PORT=1025` и перезапустить `worker`.
  Письма видны на `http://localhost:8025`.
- **Журнал.** `EMAIL_SENDER=log` (значение по умолчанию) и `LOG_LEVEL=DEBUG`: ссылка
  целиком печатается в `docker compose logs -f worker`. Почтовый сервер не нужен вовсе.

### Сквозные тесты

```bash
cd frontend && pnpm --filter @repibot/web exec playwright install chromium
pnpm --filter @repibot/web e2e
```

Тестам нужен Docker: они поднимают собственный стек отдельным проектом `repibot-e2e`
на портах 8081 (сайт) и 8026 (Mailpit) и берут настройки из
`frontend/apps/web/e2e/stack.env`, а не из вашего `.env`. Обычный стек при этом можно
не останавливать. Остановить тестовый:

```bash
docker compose -p repibot-e2e --env-file frontend/apps/web/e2e/stack.env \
  -f compose.yml -f frontend/apps/web/e2e/compose.e2e.yml --profile dev down -v
```

## Документация

- [Архитектура платформы](docs/superpowers/specs/2026-08-04-platform-architecture-design.md)
- [Спецификация фундамента](docs/superpowers/specs/2026-08-04-foundation-design.md)
- [Спецификация идентичности](docs/superpowers/specs/2026-08-05-identity-design.md)
- [Развёртывание](docs/deployment.md)
- [Бренд-бук](docs/design/repibot-brandbook.md)

## Лицензия

AGPL-3.0. См. [LICENSE](LICENSE).
