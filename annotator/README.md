# Spectrogram Annotator

Web app for labeling spectrogram images (bounding boxes + classes) in labeling experiments. Persian/RTL UI, Jalali dates,
role-based access. Runs fully offline on one machine.

```
browser ──https──► web  (nginx:  React app │ /api → api │ :9443 → minio)
                    │
                    ├─ api ───► postgres        FastAPI, async SQLAlchemy
                    │   └────► minio            images, thumbnails (private buckets, presigned URLs)
                    └─ worker ► postgres        procrastinate: daily cleanup (no Redis)
```

| Folder | What |
|---|---|
| `frontend/` | React + Vite + Tailwind. `Dockerfile` builds it and bakes it into `nginx:1.27-alpine` with `nginx/default.conf.template` |
| `backend/` | FastAPI API, Alembic migrations, worker, CLI, tests ([README](backend/README.md)) |
| `docker-compose.yml` | The whole stack: `web`, `api`, `worker`, `postgres`, `minio` + one-shots `migrate`, `minio-init` |
| `scripts/gen-certs.sh` | Self-signed TLS certificate for `APP_HOST` |
| `annotator-features.md`, `backend-stack.md`, `frontend-stack.md` | Specification and design notes |

## Run it

Base images are the ones already on this machine (`nginx:1.27-alpine`, `postgres:16`, `minio/minio`, `minio/mc`,
`python:3.12-slim`, `node:20-alpine`). **Building** `api` and `web` downloads pip/npm packages once; **running** needs no internet.

```bash
cp .env.example .env                 # fill in every empty value (openssl rand -base64 32)
./scripts/gen-certs.sh               # uses APP_HOST from .env; writes ./certs (git-ignored)
docker compose up -d --build
docker compose run --rm api python -m app.cli create-admin      # prompts for username + password
# open https://<APP_HOST>:<HTTPS_PORT>   (accept the self-signed certificate once, or import certs/fullchain.pem)
```

Ports (all configurable in `.env`): `80` → redirect, `443` → app, `9443` → MinIO for the browser's presigned uploads/downloads.
Postgres, MinIO and the API are **not** published on the host.

`APP_HOST` must be the name or IP browsers actually use: the TLS certificate, the presigned URLs and the S3 CORS rule all derive from it.
Changing it means re-running `gen-certs.sh` and `docker compose up -d`.

### Everyday commands

```bash
docker compose ps                                  # health of every service
docker compose logs -f api web worker              # JSON logs
docker compose run --rm api python -m app.cli reset-password <user>     # locked-out admin recovery
docker compose up -d --build web                   # after frontend changes
docker compose down                                # stop (data stays in the pgdata / miniodata volumes)
```

**There are no automated backups.** `docker compose down -v` deletes all images, annotations and users.
Failed-login lockout (5 attempts / 15 min per user) clears itself; to clear it immediately:
`docker compose exec postgres psql -U $POSTGRES_USER $POSTGRES_DB -c "delete from login_attempts"`.

## What was verified (Docker, real nginx/MinIO/Postgres; headless Chrome for the UI)

HTTP→HTTPS redirect, SPA fallback and cache headers, CSP, login + refresh cookie flags, presigned upload straight to MinIO through nginx
with CORS (foreign origin refused, wrong `Content-Type` and tampered signatures rejected), duplicate/junk/oversize upload handling,
annotation save/conflict/reload, restart persistence, idempotent re-run of `migrate` and `minio-init`, lockout not bypassable via a
spoofed `X-Forwarded-For`, and that only nginx is reachable from the host. In the browser: login, upload, create experiment, draw a box
(autosaved), apply a colormap — with no CSP, CORS or console errors.
