# Spectrogram Annotator — Frontend

React 18 · JavaScript (JSDoc + `checkJs`) · Tailwind CSS v4 · Vite. Persian/RTL-first, Jalali dates, fully offline (no CDN, fonts bundled).

## Quick start

```bash
pnpm install
pnpm dev:mock      # runs against the built-in in-memory mock backend (login: admin/admin, annotator/password)
pnpm dev           # runs against the real API; /api is proxied to VITE_API_TARGET (default http://localhost:8000)
pnpm build         # static output in dist/
pnpm check:offline # fails if dist/ references any external URL
pnpm test          # Vitest (dates, bbox, units, store, RTL/LTR component tests)
pnpm test:e2e      # Playwright (fa + en), needs: pnpm exec playwright install chromium
pnpm lint
```

## Layout

```
src/
  app/          App (providers), router, Layout
  api/          client.js (token + refresh-on-401 + error codes), per-resource modules, mock.js
  features/     auth · images · experiments · annotate · review · users · settings
  components/ui Dialog, Pagination, JalaliRangePicker, Ltr, States
  lib/          dates (Jalali↔UTC, Asia/Tehran) · digits · bbox · units · colormap · classColors · hotkeys
  i18n/         fa.json (default), en.json
  styles/       tailwind.css (@theme tokens, dark default, [data-theme=light])
```

## Notes

- **API contract** (assumed; adjust `src/api/*.js` to match `backend-stack.md`): `POST /auth/login|refresh|logout|change-password`,
  `GET /images?page&page_size&q&from&to`, `POST /images/presign` → presigned PUT → `POST /images/{id}/complete`,
  `GET/POST /experiments`, `GET /experiments/{id}/stats|images`,
  `GET|PUT /experiments/{id}/images/{img}/annotations` (PUT sends `If-Match: <version>`; `409 conflict` opens the conflict dialog),
  `GET/POST/PATCH /users`, `GET /audit`. Errors are `{code, message}`; the UI maps `code` → `errors.<code>`.
- Boxes are stored **normalized (0–1)**; conversion lives in `lib/bbox.js`.
- Dates cross the API boundary as **UTC ISO only**; `lib/dates.js` is the single conversion point (inclusive day bounds in Asia/Tehran).
- The canvas area is explicitly `dir="ltr"`; panels around it follow the page direction.
- Access token is in memory only; the refresh token is an httpOnly cookie.
- Deviation from the spec: tests/dev use a built-in mock (`src/api/mock.js`) instead of MSW. Swapping in MSW is straightforward since all traffic goes through `api/client.js`.

## Serving (nginx image)

`Dockerfile` builds the app (with `VITE_MOCK=false`, then `pnpm check:offline`) and copies `dist/` into `nginx:1.27-alpine`; `nginx/default.conf.template` is rendered at container start. See `../README.md` for the full stack.

Generic guidance if you serve it some other way:

Serve `dist/` with `index.html` as `no-cache`, hashed assets with a long cache, `/api` → FastAPI, and a strict CSP:

```
default-src 'self'; img-src 'self' blob: data: https://MINIO_HOST; connect-src 'self' https://MINIO_HOST; style-src 'self' 'unsafe-inline'; font-src 'self'
```
