# Backend Stack — Spectrogram Annotator

Python · FastAPI · PostgreSQL · MinIO. Companion to [annotator-features.md](annotator-features.md).

## 1. Overview

```
Browser (React, RTL/Persian)
   │  HTTPS (JSON + presigned URLs)
   ▼
Reverse proxy (Caddy/Traefik/nginx) ── TLS, gzip, security headers
   ├──► FastAPI (uvicorn workers)  ──► PostgreSQL   (metadata, annotations, users,
   │         │                                       job queue, login-attempt counters)
   │         └─ presigned URLs ───────► MinIO        (original images, thumbnails, exports)
   └──► MinIO (direct presigned GET/PUT, so the API never streams image bytes)
Worker (procrastinate, Postgres-backed) ──► thumbnails, metadata extraction, exports, auto-label (YOLO/SAM)

Deployment target: a single offline machine. No Redis, no external services, no internet at runtime.
```

## 2. Recommended stack

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.12 | Same ecosystem as the existing ML code (`train_detector.py`, YOLO, SAM) |
| Framework | **FastAPI** + Pydantic v2 | Typed request/response, auto OpenAPI docs |
| Server | uvicorn (behind gunicorn or `--workers N`) | |
| DB | **PostgreSQL 16** | JSONB for metadata/attributes, strong constraints |
| ORM / migrations | **SQLAlchemy 2.0 (async)** + **Alembic** | `asyncpg` driver |
| Object storage | **MinIO** (S3 API) | `boto3` or `aioboto3`; use presigned URLs |
| Auth | **pwdlib[argon2]** (argon2id) + **PyJWT** | Access token ~15 min, refresh token in httpOnly cookie, hashed server-side, rotated |
| Jobs | **procrastinate** (Postgres-backed queue, async) | Uses `LISTEN/NOTIFY` plus `FOR UPDATE SKIP LOCKED`; no broker needed |
| Rate limits / lockout | `login_attempts` table in Postgres | Counters per username + IP with a time window; periodic purge job |
| Cache | None initially | Add in-process TTL cache (`cachetools`) only if profiling shows a need |
| Images | Pillow (+ OpenCV where needed) | Thumbnails, validation, re-encoding, metadata strip |
| Dates | `jdatetime` or `persiantools` | Used only for export manifests and reports; API speaks UTC ISO-8601 |
| Config | `pydantic-settings` | Env-driven, no secrets in repo |
| Tooling | `uv`, `ruff`, `mypy`/`pyright`, `pytest`, `httpx`, `testcontainers` | |
| Logging | `structlog` (JSON to files/stdout), request IDs | No Sentry or other hosted monitoring (offline); use local log files and `/healthz` |

## 3. Project layout

```
annotator/backend/
├── pyproject.toml
├── alembic/                  # migrations
├── app/
│   ├── main.py               # app factory, middleware, routers
│   ├── core/                 # config, security, deps, logging, errors
│   ├── db/                   # engine, session, base
│   ├── models/               # SQLAlchemy models
│   ├── schemas/              # Pydantic models
│   ├── api/v1/               # auth, users, images, experiments, classes,
│   │                         # annotations, reviews, exports, audit
│   ├── services/             # business logic (no HTTP here)
│   ├── storage/              # MinIO client wrapper (interface + impl)
│   ├── workers/              # procrastinate tasks: thumbnails, export, autolabel
│   └── exporters/            # yolo.py, coco.py, voc.py, csv.py
└── tests/
```

Keep layering strict: **router → service → repository/storage**. Routers do no business logic.

## 4. Authentication and authorization

- Login: `POST /auth/login` returns an access JWT in the body and sets the refresh token as an httpOnly, Secure, SameSite=Strict cookie. `POST /auth/refresh` rotates it. `POST /auth/logout` revokes it.
- Refresh tokens are stored hashed in a `sessions` table, which enables "log out everywhere".
- Login lockout and rate limiting use the Postgres `login_attempts` table (username + IP, sliding window). A small in-process limiter on top is fine for a single API process, but the DB is the source of truth.
- **Offline password reset:** there is no email. An Admin issues a one-time temporary password (forced change on next login). The first admin comes from the CLI, so also provide `python -m app.cli reset-password <user>` for the locked-out admin case.
- **RBAC** is a dependency: `require_role(Role.MANAGER)`. Per-experiment access uses `require_experiment_role(exp_id, min_role)`, checked against `experiment_members`.
- Every route declares its permission explicitly, and a test asserts no route is left unprotected.
- First admin is created via CLI or env (`python -m app.cli create-admin`). No default password.

## 5. Storage (MinIO)

- Buckets: `images` (originals, immutable), `thumbs`, `exports`.
- Object keys are generated server-side (`images/{yyyy}/{mm}/{uuid}.{ext}`). User filenames are stored in the DB only, never on disk or in keys.
- **Upload flow (recommended):**
  1. Client calls `POST /images/uploads` with filename, size and sha256. The API validates, checks for duplicates, and returns a presigned PUT URL plus an `image_id` in `pending` state.
  2. Client PUTs directly to MinIO. For large files, use multipart.
  3. Client calls `POST /images/{id}/complete`. A worker validates magic bytes, decodes with Pillow, extracts width/height, generates the thumbnail, and flips the status to `ready`. It deletes the object if validation fails.
- Reads use short-lived presigned GET URLs (e.g. 5 min). MinIO is not exposed publicly except through the proxy.
- Simpler MVP alternative: stream the upload through FastAPI (`UploadFile`) with a size cap. Keep the storage interface identical so you can switch later.

## 6. Database

Use the data model in [annotator-features.md §13](annotator-features.md). Implementation notes:

- All timestamps are `timestamptz` in UTC. Jalali conversion happens in the UI. For date-range filters the client sends Gregorian ISO instants, with day boundaries computed in `Asia/Tehran`.
- Boxes are stored as normalized `x, y, w, h` (REAL, 0–1) with `CHECK` constraints for bounds. Pixel coords are derived from image width/height.
- Soft delete (`deleted_at`) on images, boxes and experiments, with partial indexes that exclude deleted rows.
- Indexes:
  - `images(uploaded_at DESC)`, `images(sha256)` unique
  - `experiment_images(experiment_id, status)`
  - `bounding_boxes(experiment_image_id)`
  - `audit_log(at DESC, user_id)`
- Concurrency: `experiment_images.version` for optimistic locking. Saves send `If-Match: <version>` and return `409` on conflict.
- Pagination uses `limit/offset` with a total count. Switch to keyset pagination on `(uploaded_at, id)` if the library grows past roughly 100k images.
- Filtering is by Gregorian instants: `?uploaded_from=...&uploaded_to=...&status=...&uploader=...&q=...`.

## 7. API design (v1, REST, JSON)

```
POST   /auth/login | /auth/refresh | /auth/logout | /auth/change-password
GET    /users            POST /users        PATCH/DELETE /users/{id}      # admin
GET    /images           (pagination, date range, filters)
POST   /images/uploads   POST /images/{id}/complete   DELETE /images/{id}
GET    /images/{id}/url                                   # presigned GET
GET    /experiments      POST /experiments  PATCH/DELETE /experiments/{id}
GET/POST/PATCH/DELETE /experiments/{id}/classes
POST   /experiments/{id}/images                           # add from library
GET    /experiments/{id}/images                           # queue, status filter
GET    /experiments/{id}/images/{img}/annotations
PUT    /experiments/{id}/images/{img}/annotations         # replace set, If-Match
POST   /experiments/{id}/images/{img}/review
POST   /experiments/{id}/exports    GET /exports/{job}    # async job
GET    /audit                                            # admin
GET    /healthz  /readyz
```

- Prefer a **single `PUT` of the full annotation set per image** (small payloads, atomic, easy undo/redo and autosave) over per-box CRUD.
- Consistent error envelope with machine-readable `code` (the frontend maps codes to Persian messages). The backend never returns user-facing Persian text.
- Version the API under `/api/v1`. Disable `/docs` in production or protect it.

## 8. Background jobs

| Job | Trigger |
|---|---|
| Validate image, make thumbnail, extract metadata | after upload complete |
| Export (YOLO/COCO/VOC/CSV + split) → ZIP to `exports/` | export request |
| Auto-label (YOLO weights / SAM, reusing `autolabeling/`) | manual, P2 |
| Purge soft-deleted objects, expire sessions | scheduled |

GPU inference (auto-label) should run as a separate worker image so the API image stays small. Jobs are rows in Postgres (`procrastinate_jobs`), so queue state survives restarts and is visible with plain SQL. Add scheduled tasks via procrastinate's periodic tasks (no cron or Celery beat). Model weights (`yolo26s.pt`, `mobile_sam.pt`) are mounted from a local volume, never downloaded at runtime.

## 9. Security checklist

- Argon2id, password policy, lockout, refresh rotation and revocation
- Strict CORS allow-list, CSRF protection for cookie endpoints, security headers
- Upload limits at the proxy and app. Validate magic bytes, decode and re-encode with Pillow, set a decompression-bomb limit (`Image.MAX_IMAGE_PIXELS`), strip EXIF
- Parameterized queries only (SQLAlchemy). Authorization is checked in services, not just routes
- Secrets from env or Docker secrets. Rotate `JWT_SECRET`. MinIO credentials are scoped to the app (not root)
- Audit-log every auth event and every create/update/delete
- Offline: vendor or mirror Python wheels and Docker images (`pip download` / `docker save`) so the machine can be rebuilt without internet. Run `pip-audit` on a connected machine before each transfer

## 10. Deployment (Docker Compose)

Services: `proxy`, `api`, `worker`, `postgres`, `minio`, optional `worker-gpu`. (No Redis.)

- Named volumes for `postgres` and `minio`. Healthchecks on all services. The `api` container runs `alembic upgrade head` at start (or as a one-shot job).
- Nightly `pg_dump` plus `mc mirror` to a second local disk or external drive. There is no cloud backup, so document a restore drill.
- TLS uses an internal CA or self-signed certificate (Caddy `tls internal`), since Let's Encrypt needs internet.
- Pre-pull and pin all image tags, and ship fonts (Vazirmatn) and all frontend assets locally, with no CDN references.
- Environment-driven config. Provide `.env.example` and no real secrets in git.

## 11. Testing

- `pytest` + `httpx.AsyncClient` against real Postgres and MinIO via `testcontainers`.
- Must-have tests:
  - Permission matrix (each role × each endpoint).
  - Annotation save/conflict (`409`) and bounds validation.
  - Date-range filter at Tehran day boundaries, including the DST-free post-2022 rule and Jalali leap days.
  - Upload validation (bad magic bytes, oversized, duplicate).
  - Exporter output correctness (YOLO normalization, COCO bbox format `[x,y,w,h]` in pixels).

## 12. Decisions and trade-offs

- **FastAPI + async SQLAlchemy:** good fit and typed, but async sessions need discipline. Don't mix blocking Pillow or ML work into request handlers. Use workers.
- **Presigned direct upload:** scales and keeps the API light, at the cost of an extra complete step and a pending-state cleanup job.
- **No Redis (decided, offline machine):** jobs run on Postgres via procrastinate and rate limits live in a table. This means one fewer service to ship and back up. The trade-off is slightly higher DB load and no sub-millisecond counters, which is irrelevant at annotation-team scale. If the app ever moves to a multi-node cloud deployment, the job layer is the only part to revisit.
- **Full-set `PUT` for annotations** assumes tens, not thousands, of boxes per image, which holds for spectrograms.
- **MinIO licensing/maintenance:** check the current MinIO edition and license terms before committing. Because all access goes through the S3 API behind `storage/`, swapping to another S3-compatible store (e.g. SeaweedFS, Garage) is a config change.

## 13. Open questions

- Single offline machine is decided. Is there more than one machine on the LAN, with browsers reaching the server by IP or hostname? (Decides the TLS certificate setup.)
- Expected image count and resolution? (Decides offset vs keyset pagination and the tiling or preview strategy.)
- Is a GPU available for auto-labeling workers?
