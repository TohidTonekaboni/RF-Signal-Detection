# syntax=docker/dockerfile:1
# Web image = built React app + nginx (static files, /api reverse proxy, MinIO TLS port).
# Both base images are the ones already present locally; override with --build-arg / .env.
ARG NODE_TAG=20-alpine
ARG NGINX_TAG=1.27-alpine

FROM node:${NODE_TAG} AS build
WORKDIR /app
# pnpm 9 reads lockfileVersion 9.0. Needs registry access at BUILD time only; the running stack is offline.
RUN npm install -g pnpm@9
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
# Real API (never the in-memory mock), then fail the build if the bundle references any external URL.
ENV VITE_MOCK=false
RUN pnpm build && pnpm check:offline

FROM nginx:${NGINX_TAG}
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
