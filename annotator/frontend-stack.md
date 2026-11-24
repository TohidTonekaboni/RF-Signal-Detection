# Frontend Stack — Spectrogram Annotator

React · JavaScript · Tailwind CSS · Vite. Companion to [annotator-features.md](annotator-features.md) and [backend-stack.md](backend-stack.md).

Constraints that drive every choice below:
- **Persian (Farsi), RTL-first**, with Jalali (شمسی) dates and Persian digits.
- **Offline deployment:** no CDN, no Google Fonts, no runtime internet. Everything is bundled and served locally.
- **A canvas-heavy annotation workspace** is the hero screen. Its time axis runs left→right even inside the RTL page.

## 1. Recommended stack

| Concern | Choice | Notes |
|---|---|---|
| Framework | **React 18/19** (function components, hooks) | |
| Language | **JavaScript (ES2023)** + JSDoc types | Add `// @ts-check` / `checkJs` in `jsconfig.json` for editor type-checking without TypeScript |
| Build | **Vite** | Fast dev server, static output served by the proxy; set `base` and proxy `/api` in dev |
| Styling | **Tailwind CSS v4** | Use **logical utilities** (`ms-*`, `me-*`, `ps-*`, `pe-*`, `start-*`, `end-*`, `text-start`) so RTL works without `rtl:` overrides |
| Components | **shadcn/ui** pattern (Radix UI primitives, copied into the repo) | Accessible dialogs, dropdowns, tabs, tooltips, popovers; no runtime CDN. Radix supports `dir="rtl"` via `DirectionProvider` |
| Icons | **lucide-react** | Flip directional icons in RTL with `rtl:-scale-x-100` |
| Routing | **React Router** | Route-level code splitting, protected routes by role |
| Server state | **TanStack Query** | Caching, pagination (`keepPreviousData`), mutations, optimistic updates, retry |
| Client state | **Zustand** | Workspace state (tool, selection, zoom, undo/redo stack, unsaved changes), auth session, UI prefs |
| Forms | **React Hook Form** + **Zod** | Login, experiments, class editor, user admin. Zod schemas mirror backend validation |
| HTTP | `fetch` wrapper (or **ky**) | One client: attaches access token, refreshes on `401`, maps error `code` → Persian message |
| i18n | **i18next** + **react-i18next** | `fa` default, `en` secondary. Bundled JSON, no remote loading |
| Jalali dates | **date-fns-jalali** (formatting/math) + **react-multi-date-picker** with `react-date-object` persian calendar/locale | Convert to/from UTC ISO at the API boundary only |
| Persian digits | Small util (`toPersianDigits`) + `Intl.NumberFormat('fa-IR')` | Toggle in settings |
| Font | **Vazirmatn** via `@fontsource-variable/vazirmatn` | Bundled woff2; mono: `@fontsource/jetbrains-mono` |
| Annotation canvas | **react-konva** (Konva) | Layers, drag/resize transformers, hit testing, zoom/pan. See §4 |
| Charts | **Recharts** (or **visx** for more control) | Dashboard only. Keep it RTL-aware (reverse x-axis, Persian tick labels) |
| Upload | **react-dropzone** + XHR/`fetch` | Presigned PUT to MinIO, per-file progress, retry, folder picker (`webkitdirectory`) |
| Hotkeys | **react-hotkeys-hook** | Scoped to the workspace; shortcut cheat-sheet generated from one registry |
| Virtualization | **TanStack Virtual** | Image grid/filmstrip with thousands of items |
| Toasts | **sonner** | RTL-compatible |
| Utilities | `clsx` + `tailwind-merge` (`cn()` helper), `immer` (undo/redo patches), `nanoid` | |

## 2. Tooling

| Tool | Purpose |
|---|---|
| **ESLint** (flat config) + `eslint-plugin-react-hooks`, `jsx-a11y`, `tailwindcss` | Lint. Add a rule or review habit that flags physical `ml-/mr-/left-/right-` classes |
| **Prettier** + `prettier-plugin-tailwindcss` | Formatting and class ordering |
| **Vitest** + **React Testing Library** + `@testing-library/user-event` | Unit/component tests |
| **MSW** | Mock the API for tests and for developing without the backend |
| **Playwright** | E2E: login, upload, Jalali filter, draw/save/delete a box, in RTL and LTR |
| **Storybook** (optional) | Component catalog for the design system, with an RTL/LTR and dark/light toolbar |
| **Husky + lint-staged** | Pre-commit lint/format |
| **pnpm** (or npm) | Package manager. Commit the lockfile |

## 3. Project layout

```
annotator/frontend/
├── index.html                 # <html lang="fa" dir="rtl">
├── vite.config.js
├── jsconfig.json              # checkJs, path alias @/ → src/
├── src/
│   ├── main.jsx
│   ├── app/                   # router, providers (Query, i18n, Direction, Theme), auth guard
│   ├── api/                   # client.js, auth.js, images.js, experiments.js, annotations.js ...
│   ├── features/
│   │   ├── auth/              # login, session, role guards
│   │   ├── images/            # library, upload drawer, filters, pagination
│   │   ├── experiments/       # list, wizard, class editor, dashboard
│   │   ├── annotate/          # workspace (see §4)
│   │   ├── review/
│   │   ├── users/             # admin + audit log
│   │   └── settings/
│   ├── components/ui/         # shadcn-style primitives
│   ├── lib/                   # cn.js, dates.js (Jalali↔UTC), digits.js, bbox.js, colormap.js
│   ├── i18n/                  # fa.json, en.json, index.js
│   ├── styles/                # tailwind.css (@theme tokens), fonts.css
│   └── assets/
└── tests/ (unit) and e2e/
```

Group by **feature**, not by file type. Shared primitives stay in `components/ui`.

## 4. Annotation workspace architecture

**Rendering:** `react-konva` with three layers: (1) image layer, (2) boxes layer (rectangles, labels, `Transformer` for 8 handles), (3) overlay layer (crosshair, drawing preview, HUD guides). Rulers, colorbar and mini-map are plain React/SVG next to the stage.

**Direction:** the canvas container sets `dir="ltr"` explicitly, because time runs left→right and frequency bottom→top. Panels around it stay RTL. Never rely on inherited direction inside the stage.

**Coordinates:** store boxes **normalized (0–1)** relative to the image, exactly as the backend does. Convert to stage pixels only when rendering, using the current zoom/pan transform. Keep conversion in `lib/bbox.js` with unit tests (round-trip, clamping to bounds, min size).

**State (Zustand store `useWorkspaceStore`):**
- `boxes[]`, `imageLabels[]`, `selection`, `tool`, `activeClass`, `viewport {scale, x, y}`, `display {brightness, contrast, gamma, colormap, invert}`
- `history` (past/future patch stacks via immer `produceWithPatches`) for undo/redo
- `dirty`, `version` (for `If-Match`), `saveStatus`

**Display adjustments** (brightness/contrast/gamma/colormap/invert) are applied non-destructively: Konva filters for simple cases, or a WebGL/`OffscreenCanvas` pass if large images feel slow. The original bytes are never modified.

**Saving:** debounced autosave (e.g. 2 s after the last change) plus an explicit Save, both calling `PUT …/annotations` with the full set and the current `version`. On `409`, show the conflict dialog (reload theirs / overwrite mine). Warn on route change or tab close with unsaved changes (`beforeunload` + router blocker).

**Performance:** load the full-size image via a presigned URL, show the thumbnail first, then swap. Use `Konva.Image` with `imageSmoothingEnabled=false` at high zoom. Prefetch the next image in the queue. For very large spectrograms, request a downscaled preview first.

**Physical units:** if image metadata has duration/bandwidth/center-frequency, the HUD maps pixel → seconds and Hz through a pure function in `lib/units.js` (tested). If metadata is missing, show pixels only.

**Alternative considered:** a hand-rolled `<canvas>` or SVG overlay avoids a dependency, but you then write hit testing, transformers and handle logic yourself. Konva is recommended unless bundle size becomes a concern. Everything is behind `features/annotate/`, so it can be swapped.

## 5. RTL, Persian and Jalali specifics

- `<html lang="fa" dir="rtl">` set from the i18n language. `DirectionProvider` (Radix) and the date picker receive the same direction.
- **Tailwind:** prefer logical properties (`ps-4`, `me-2`, `text-start`, `border-s`, `start-0`). Directional icons and chevrons get `rtl:-scale-x-100`. Progress bars fill with `origin-right` in RTL via logical/`rtl:` variants.
- **Bidi isolation:** wrap technical values (filenames, `2.437 GHz`, coordinates, shortcut keys) in a small `<Ltr>` component (`<bdi dir="ltr">`) so mixed lines don't scramble.
- **Digits:** all displayed numbers pass through a `fmtNumber()` that respects the user's digit setting (Persian by default). Mono readouts in the canvas HUD may stay Latin digits for unit readouts. Make that a visible, consistent choice.
- **Jalali:**
  - The API sends and receives **UTC ISO-8601 only**. `lib/dates.js` is the single place that converts: `toJalaliString(iso)`, `jalaliRangeToUtc({from, to})` (inclusive day boundaries in `Asia/Tehran`).
  - The date-range filter keeps its state as Jalali date objects and sends UTC instants in the query string. Cover this with unit tests, including month ends (۳۱/۳۰ days, اسفند leap years) and day-boundary edges.
  - Week starts on Saturday. Persian month and weekday names come from the library locale.
- **Typography:** Vazirmatn with `leading-relaxed`/`1.7` for Persian blocks. Don't apply `tracking-*` (letter-spacing) to Persian text because it breaks letter joining.
- **i18n keys** are the source of truth for copy: no hard-coded strings in JSX. Backend returns error `code`s; the UI maps them via `errors.<code>`.

## 6. Design tokens (Tailwind v4 `@theme`)

Define colors, radii and fonts once in `styles/tailwind.css`, with dark as default and a light override via `[data-theme="light"]`. Tokens: `--color-bg`, `--color-panel`, `--color-panel-2`, `--color-border`, `--color-accent` (cyan), `--color-warn` (amber), `--color-select` (magenta), `--font-sans` (Vazirmatn), `--font-mono`. Class colors for boxes come from a single colorblind-safe array in `lib/classColors.js`, and the user-picked class color is validated against minimum contrast on viridis/magma/turbo thumbnails.

## 7. Auth and authorization in the client

- Access token held **in memory** (Zustand), refresh token in an httpOnly cookie managed by the backend. No tokens in `localStorage`.
- On load, call `/auth/refresh` to restore the session. The fetch client retries once after a refresh on `401`, then redirects to login.
- `<RequireRole roles={[…]}>` route guard and a `useCan(permission)` hook hide UI. This is **cosmetic only**, because the backend enforces every permission.
- Force-change-password flow on first login and after an admin reset.

## 8. Offline build and serving

- `pnpm build` produces static assets in `dist/`, served by the `web` nginx image (`Dockerfile`, `nginx/default.conf.template`) alongside `/api` → FastAPI and the MinIO presigned-URL port.
- **No external URLs** in the bundle: fonts via `@fontsource*`, icons via `lucide-react` (inline SVG), no analytics, no CDN scripts. Add a CI/grep check for `https://` in `dist/`.
- Commit `pnpm-lock.yaml`, and keep an offline package cache (`pnpm fetch` / a mirrored store) so the build can run on a machine without internet.
- Use content-hashed filenames and a long cache lifetime, with `index.html` as `no-cache`.
- Serve behind the internal-CA TLS from the backend doc. Set a strict **CSP** (`default-src 'self'`; `img-src 'self' blob: data:` and the MinIO origin; `connect-src 'self'` plus the MinIO origin).

## 9. Testing priorities

- `lib/dates.js`: Jalali ↔ UTC, range boundaries, leap years. `lib/bbox.js`: normalize/denormalize, clamp, min size. `lib/units.js`: pixel → time/frequency.
- Workspace store: undo/redo, dirty tracking, conflict handling (MSW returning `409`).
- Component tests in **both `dir="rtl"` and `dir="ltr"`** for Library, pagination, date picker and class editor.
- Playwright E2E: login → upload → filter by Jalali range → create experiment → draw/edit/delete box → autosave → export. Run once in `fa` and once in `en`.
- Accessibility: `jsx-a11y` lint plus axe checks in Playwright on main screens.

## 10. Decisions and trade-offs

- **JavaScript, not TypeScript:** faster to start, but type errors surface later. `checkJs` with JSDoc recovers much of the safety. Zod schemas give runtime validation at the API boundary. Migrating to TypeScript later is incremental (`.jsx` → `.tsx` file by file).
- **shadcn/ui over a full component library (MUI/Ant):** you own the code, there's no CDN or runtime theme dependency, and Tailwind logical utilities make RTL natural. Cost: you maintain the components. Ant Design has strong built-in RTL and table/date components but is heavier and harder to restyle toward the instrument-panel look.
- **react-multi-date-picker for Jalali:** mature Persian support and range mode. Its styling needs theming to match the dark UI. Wrap it behind `components/ui/JalaliRangePicker` so it can be replaced.
- **Zustand + TanStack Query** instead of Redux: less boilerplate, and each has a clear role (client vs server state).
- **react-konva** adds bundle weight but saves substantial custom canvas work.

## 11. Open questions

- Should unit readouts in the canvas HUD use Persian or Latin digits by default?
- Are image sizes large enough (e.g. >8000 px wide) to require tiled loading?
- Do you want Storybook (extra tooling, useful if the Claude Design mock is turned into a component library), or skip it for the MVP?
- Is a PWA/offline cache of the app shell useful, or is the server always reachable on the LAN?
