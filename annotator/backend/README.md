# Spectrogram Annotator — Backend

FastAPI · async SQLAlchemy · PostgreSQL · MinIO (S3) · procrastinate (Postgres job queue, no Redis).
Written to match the React client in `../frontend` (routes under `/api`, error envelope `{code, message}`).

## Layout

```
app/
  main.py            app factory, request-id/access-log middleware, routers under /api, /healthz /readyz
  core/              config (env), security (argon2, JWT, refresh tokens), deps (auth/RBAC), errors, logging
  db/                engine/session, UTC datetime type
  models.py          users, sessions, login_attempts, images, experiments, classes,
                     experiment_images (membership + annotation version), bounding_boxes, audit_log
  schemas.py         request/response models (validation mirrors the frontend's zod schemas)
  api/               auth, users, images, experiments, annotations, audit, health
  services/          imaging (validate/thumbnail), audit, housekeeping, serialize
  storage/s3.py      Storage interface + boto3/MinIO implementation (presigned URLs)
  workers/           procrastinate app + daily housekeeping task
  cli.py             create-admin, reset-password
alembic/             migrations (0001 = full schema)
tests/               64 tests; SQLite by default, real Postgres with TEST_DATABASE_URL
```

## Run (via the compose file one level up)

```bash
cd .. && cp .env.example .env     # fill in secrets
./scripts/gen-certs.sh            # self-signed TLS cert
docker compose up -d --build      # migrate → api/worker/web (the web image builds the frontend)
docker compose run --rm api python -m app.cli create-admin
```

Recovery when the only admin is locked out: `docker compose run --rm api python -m app.cli reset-password <user>`.

## Tests

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                   # SQLite + in-memory object store, no services needed
TEST_DATABASE_URL=postgresql+asyncpg://user:pw@host/db pytest   # same suite on Postgres
```

The suite builds the schema with the real Alembic migration and asserts the migration matches the models.

## API summary

| Route | Who |
|---|---|
| `POST /api/auth/login · refresh · logout · change-password`, `GET /api/auth/me` | login public; rest authenticated |
| `GET/POST /api/users`, `PATCH /api/users/{id}`, `POST /api/users/{id}/reset-password`, `GET /api/audit` | admin |
| `GET /api/images?page&page_size&q&from&to`, `GET /api/images/{id}` | any role |
| `POST /api/images/presign` → browser PUT to MinIO → `POST /api/images/{id}/complete`, `PATCH /api/images/{id}` | admin, annotator |
| `DELETE /api/images/{id}` (soft delete) | admin |
| `GET /api/experiments[/{id}[/stats\|/images]]` | any role |
| `POST /api/experiments`, `PUT /api/experiments/{id}`, `POST /api/experiments/{id}/images` | admin |
| `GET …/experiments/{e}/images/{i}/annotations` | any role |
| `PUT …/annotations` with `If-Match: <version>` | admin, annotator |

Dates cross the API as UTC ISO-8601 only. Boxes are normalized 0–1. Errors: `401 unauthorized`, `403 forbidden | password_change_required`, `404 not_found`, `409 conflict | duplicate_image | username_taken | last_admin | class_in_use`, `413 file_too_large`, `415 unsupported_media_type`, `422 validation_error | invalid_image | weak_password`, `428 precondition_required`, `429 too_many_attempts`.

## Known gaps / things to know

- **Frontend i18n:** `src/i18n/*.json` only has `errors.*` for `invalid_credentials, forbidden, not_found, conflict, validation_error, network, unauthorized, unknown`. The other codes above fall back to "unknown error" until translations are added.
- **Reset password:** the API returns `{temporary_password}`, but `UsersPage.jsx` ignores the response, so the admin never sees it. The UI needs a dialog to show it once.
- **Uploads:** the client must send the same `Content-Type` it declared in `/presign` (it does); the presigned URL is signed for it.
- **Verified end to end** on the full Docker stack (real nginx, MinIO, PostgreSQL 16) with curl and with headless Chrome driving the React UI: login, upload via presigned PUT through nginx :9443 (incl. CORS), annotate/save/reload, restart persistence. See `../README.md`.
- Single API process assumed for the in-DB login throttling (it is DB-backed, so multiple workers also work).
