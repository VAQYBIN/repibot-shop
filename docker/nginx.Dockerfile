# syntax=docker/dockerfile:1

# Статика MiniApp собирается здесь же и уезжает внутрь образа nginx:
# отдельный контейнер ради набора файлов не нужен.
FROM node:24-alpine AS miniapp

ENV PNPM_HOME=/pnpm
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

WORKDIR /repo

COPY frontend/pnpm-workspace.yaml frontend/pnpm-lock.yaml frontend/package.json frontend/.npmrc ./
COPY frontend/packages/config/package.json packages/config/
COPY frontend/packages/core/package.json packages/core/
COPY frontend/packages/ui/package.json packages/ui/
COPY frontend/apps/miniapp/package.json apps/miniapp/

RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile --filter @repibot/miniapp...

COPY frontend/ ./

RUN pnpm --filter @repibot/miniapp build


FROM nginx:1.27-alpine AS runtime

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=miniapp /repo/apps/miniapp/dist /usr/share/nginx/html/app

EXPOSE 80
