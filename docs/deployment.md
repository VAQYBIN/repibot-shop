# Развёртывание

## Что понадобится

- Сервер с Docker и Docker Compose.
- Домен с сертификатом TLS.
- Панель Remnawave 2.8.1 — на этом же сервере или на другом.
- Бот, созданный в @BotFather.

## 1. Панель Remnawave

Создайте в панели API-токен (раздел API Tokens) и запишите его в `REMNAWAVE_TOKEN`.

Адрес панели зависит от размещения:

- Панель на другом сервере: `REMNAWAVE_BASE_URL=https://panel.example.org`
- Панель рядом: `REMNAWAVE_BASE_URL=http://remnawave:3000`, запуск с оверлеем
  `docker compose -f compose.yml -f compose.local-panel.yml up -d`. Имя внешней сети
  в `compose.local-panel.yml` должно совпадать с сетью вашей панели.

## 2. Бот и вход через Telegram

В @BotFather получите токен бота — это `BOT_TOKEN`.

Вход через Telegram на сайте работает по OpenID Connect. Настройки задаются
**в мини-приложении @BotFather**, через обычный чат этот раздел недоступен:

1. Откройте мини-приложение BotFather, выберите бота.
2. Bot Settings → Web Login.
3. Скопируйте **Client ID** и **Client Secret**.
4. В **Redirect URIs** добавьте `https://ваш-домен/auth/telegram/callback`.
5. В **Trusted Origins** добавьте `https://ваш-домен/`.

Адреса должны совпадать точно, включая протокол и завершающий слеш. Расхождение
проявляется отказом на этапе обмена кода на токен.

Client ID и Client Secret понадобятся начиная с подпроекта 1 — в фундаменте
аутентификации ещё нет, но настроить их удобно сразу.

## 3. Переменные окружения

```bash
cp .env.example .env
```

Обязательно заполнить: `BOT_TOKEN`, `BOT_WEBHOOK_SECRET`, `BOT_WEBHOOK_BASE_URL`,
`REMNAWAVE_BASE_URL`, `REMNAWAVE_TOKEN`, `JWT_SECRET`, `ENCRYPTION_KEY`,
`POSTGRES_PASSWORD`, `PUBLIC_WEB_URL`, `PUBLIC_APP_URL`.

`POSTGRES_PASSWORD` встречается дважды: отдельной переменной и внутри
`DATABASE_URL`. Значения должны совпадать, иначе миграции не подключатся к базе.

Секреты генерируются так:

```bash
openssl rand -hex 32
```

`BOT_WEBHOOK_SECRET` Telegram присылает в заголовке `X-Telegram-Bot-Api-Secret-Token`
на каждом запросе; это единственное, что подтверждает подлинность вебхука. Меняя
значение, перезапустите бота — он переустанавливает вебхук на старте.

В самом адресе секрета нет. Вебхуки приходят на постоянные пути вида
`/webhook/<источник>`: сейчас это `/webhook/telegram`, позже добавится
`/webhook/yookassa`. URL целиком попадает в журнал доступа Nginx, в панель
туннеля при локальной отладке и в любой промежуточный прокси — секрету там
не место.

## 4. TLS

Конфигурация Nginx в репозитории слушает только 80 порт: сертификаты выпускаются
на конкретный домен, и держать в открытом проекте чужой домен бессмысленно.

Варианты:

- Внешний обратный прокси (Caddy, Traefik) перед контейнером `nginx`.
- Certbot и монтирование сертификатов в контейнер `nginx` с добавлением
  секции `listen 443 ssl` в `docker/nginx.conf`.

Telegram принимает вебхуки только по HTTPS — без TLS бот работать не будет.

## 5. Запуск

```bash
docker compose build
docker compose up -d
docker compose ps
curl https://ваш-домен/health
```

Ожидаемо: все сервисы в состоянии `running`, кроме `migrate` — он одноразовый
и завершается кодом 0. Проверка живости возвращает
`{"status":"ok","database":true,"valkey":true}`.

## 6. Обновление

```bash
git pull
docker compose build
docker compose up -d
```

Миграции применяет сервис `migrate` до старта остальных — вручную ничего запускать
не нужно.

## Диагностика

| Симптом | Причина |
|---|---|
| `migrate` завершается с ошибкой | Недоступен Postgres или неверный `DATABASE_URL` |
| `/health` отдаёт `database: false` | Контейнер базы не поднялся, смотрите `docker compose logs postgres` |
| Бот не отвечает | Проверьте `BOT_WEBHOOK_BASE_URL`, TLS и `docker compose logs bot` |
| Бот пишет `Unauthorized: invalid token specified` | Неверный `BOT_TOKEN`, возьмите его заново у @BotFather |
| Задачи не выполняются | Работать должны оба сервиса: `worker` и `scheduler` |
| Панель не отвечает | Проверьте `REMNAWAVE_TOKEN` и сетевую доступность из контейнера `api` |
