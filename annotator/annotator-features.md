# Spectrogram Annotator — Feature Specification

Web application for annotating spectrogram images (bounding boxes for detection, labels for classification) across multiple labeling experiments, with authentication, authorization and user management.

Priority legend: **P0** = MVP, **P1** = needed soon after, **P2** = nice to have.

---

## 1. Authentication

| ID | Feature | Pri |
|----|---------|-----|
| A1 | Login with username/email + password; logout | P0 |
| A2 | Short-lived access token + refresh token (httpOnly cookie); automatic refresh | P0 |
| A3 | Password hashing (argon2/bcrypt), password policy, change password | P0 |
| A4 | Forgot / reset password (email link or admin-issued temporary password for offline deployments) | P1 |
| A5 | Login rate limiting and temporary lockout after repeated failures | P1 |
| A6 | Active sessions list, revoke session / "log out everywhere" | P2 |
| A7 | Optional 2FA (TOTP); optional SSO (LDAP/OIDC) for institutional deployments | P2 |

## 2. Authorization (RBAC)

Roles are global; some permissions are also scoped per experiment (membership).

| Role | Capabilities |
|------|--------------|
| **Admin** | Everything: manage users, roles, all experiments, system settings, audit log |
| **Manager** | Create/own experiments, define classes, assign annotators/reviewers, assign images, review, export |
| **Reviewer** | View all annotations in assigned experiments, approve / reject / correct |
| **Annotator** | Create/edit/delete **own** annotations on images assigned to them in experiments they are members of |
| **Viewer** | Read-only access to assigned experiments |

| ID | Feature | Pri |
|----|---------|-----|
| Z1 | Role-based access enforced on the **backend** for every endpoint (UI hiding is cosmetic only) | P0 |
| Z2 | Per-experiment membership (user ↔ experiment ↔ role) | P0 |
| Z3 | Annotators cannot see/edit other annotators' work unless experiment allows it | P1 |
| Z4 | Locked experiments/images are read-only for everyone except Admin/Manager | P1 |

## 3. User Management (Admin)

| ID | Feature | Pri |
|----|---------|-----|
| U1 | Create / edit / deactivate (soft-disable) / delete users | P0 |
| U2 | Assign role; force password change on first login | P0 |
| U3 | User list with search, filter by role/status, pagination | P0 |
| U4 | User profile: name, email, avatar, preferred language, preferred calendar (Jalali/Gregorian) | P1 |
| U5 | Invite users by email / invite link | P2 |
| U6 | Per-user activity summary (annotations made, time spent, review acceptance rate) | P2 |
| U7 | First-run bootstrap: create initial admin via env var/CLI (no default password) | P0 |

## 4. Image Upload & Library

| ID | Feature | Pri |
|----|---------|-----|
| I1 | **Upload icon** opens a native file picker; select multiple images (and optionally a whole folder via `webkitdirectory`) | P0 |
| I2 | Drag-and-drop upload as an additional path | P1 |
| I3 | Accepted formats: PNG, JPG/JPEG (optionally TIFF, NPY for raw spectrograms); size limit; client + server validation (magic bytes, not just extension) | P0 |
| I4 | Upload progress per file, retry on failure, cancel; chunked/parallel upload for large batches | P1 |
| I5 | Duplicate detection via content hash (SHA-256); warn/skip | P1 |
| I6 | Server generates thumbnails and extracts metadata (width, height, size, hash) | P0 |
| I7 | Upload timestamp stored in UTC; **displayed in Jalali (شمسی)** | P0 |
| I8 | Image list as grid/table with thumbnails, filename, upload date (Jalali), uploader, annotation status | P0 |
| I9 | **Pagination** (page size selectable: 20/50/100; total count; jump to page) | P0 |
| I10 | **Filter by upload date range** using a Jalali date-picker (from/to); filters converted to Gregorian/UTC on the server | P0 |
| I11 | Additional filters: uploader, filename search, tag, annotation status (unlabeled / in progress / done / reviewed), assigned to, experiment | P1 |
| I12 | Sort by upload date, name, status | P1 |
| I13 | Delete image(s) (soft delete, admin/manager only, with confirmation) | P0 |
| I14 | Image-level metadata/tags (e.g. band, sample rate, center frequency, capture device, source dataset) — editable, filterable | P1 |
| I15 | Import metadata via CSV (filename → metadata) | P2 |

### Jalali (شمسی) calendar requirements
- Date picker with Persian month names, Saturday as week start, RTL layout, Persian digits (toggleable).
- Store **UTC ISO-8601** in DB; convert at the edge (UI) and for filter parameters. Never store Jalali strings.
- Correct handling of Iranian time zone (Asia/Tehran) and day boundaries when filtering "from 1403/05/01 to 1403/05/10" (inclusive range 00:00 → 23:59:59 Tehran time).
- Libraries to evaluate: `jalaali-js`, `date-fns-jalali`, `react-multi-date-picker` (persian calendar) or equivalent.
- Gregorian display option for users who prefer it (U4).

## 5. Labeling Experiments

An **experiment** is an independent labeling project with its own task type, class schema, images and members.

| ID | Feature | Pri |
|----|---------|-----|
| E1 | Create / edit / archive / delete experiments (name, description, task type, owner, created date in Jalali) | P0 |
| E2 | Task types: **Object detection** (bounding boxes + class), **Image classification — single-label**, **Image classification — multi-label**; (P2: both at once, segmentation polygons, time-frequency region of interest) | P0 |
| E3 | Define **classes** per experiment: name, color, optional hotkey (1–9), description, optional parent group | P0 |
| E4 | Separate **class sets** for box labels vs. image-level labels in the same experiment (e.g. boxes: `LTE`, `WiFi`, `Bluetooth`; image-level: `congested`, `clean`, `jammed`) | P0 |
| E5 | Edit/rename/reorder/merge classes; deleting a class in use requires remap or confirmation | P1 |
| E6 | Optional **attributes** per box (e.g. `occluded`, `truncated`, `low-SNR`, free-text note, confidence 1–5) | P1 |
| E7 | Add images to an experiment from the library (select by filter, selection, or "all matching filter") | P0 |
| E8 | Clone experiment (schema only, or schema + images) | P2 |
| E9 | Import class schema from JSON/YAML/COCO categories; export schema | P1 |
| E10 | Experiment dashboard: total images, % annotated, per-class counts, per-user progress | P1 |
| E11 | Experiment settings: allow overlapping boxes, require ≥1 label before "done", min box size, review required (yes/no) | P1 |
| E12 | Image-to-annotator assignment (manual, round-robin, or by batch) | P1 |

## 6. Annotation Workspace

| ID | Feature | Pri |
|----|---------|-----|
| W1 | Canvas viewer with zoom (wheel/pinch), pan, fit-to-screen, 1:1 pixel view | P0 |
| W2 | Draw bounding box by click-drag; select, move, resize (8 handles), delete | P0 |
| W3 | Assign class to box (picker or number hotkeys); change class later | P0 |
| W4 | Image-level class label(s) panel (radio for single-label, checkboxes for multi-label) | P0 |
| W5 | **Save** annotations to backend (explicit Save + autosave every N seconds / on change); unsaved-changes warning | P0 |
| W6 | **Edit** existing annotations; **delete** single box or clear all (confirmation) | P0 |
| W7 | Undo / redo (Ctrl+Z / Ctrl+Shift+Z), within session | P0 |
| W8 | Next / previous image navigation (arrow keys); jump to next unlabeled; image queue sidebar | P0 |
| W9 | Annotation list sidebar: per-box class, visibility toggle, lock, delete, click to focus | P0 |
| W10 | Keyboard shortcuts for everything (draw, delete, class select, save, next/prev, copy/paste box); shortcut cheat-sheet overlay | P1 |
| W11 | Copy/paste boxes, duplicate box, "repeat previous image's annotations" | P1 |
| W12 | **Spectrogram-aware features**: show axis mapping — pixel → time (s) and frequency (Hz) readout when image metadata (duration, bandwidth, center freq) is known; crosshair with live coordinates | P1 |
| W13 | Display controls: brightness / contrast / gamma / colormap override / invert, applied client-side (non-destructive) | P1 |
| W14 | Box label rendering options: show/hide labels, line thickness, opacity, class color fill | P1 |
| W15 | Snap/edge assist, constrain to full-frequency-band or full-time-span (common for RF signals — box that spans the entire width/height) | P2 |
| W16 | Mark image status: *skipped*, *unsure / needs review*, *no objects (negative sample)*, *done* | P0 |
| W17 | Image comments / flags for discussion | P2 |
| W18 | Touch / tablet support | P2 |
| W19 | **Model-assisted pre-labeling**: run an existing detector (e.g. the project's YOLO weights) / auto-label (SAM-based, see `autolabeling/`) to propose boxes; annotator accepts/edits. Pre-labels flagged as `source=model` | P2 |

## 7. Annotation Storage, Versioning & Review

| ID | Feature | Pri |
|----|---------|-----|
| S1 | Persist annotations in DB: experiment, image, annotator, class, bbox (normalized + pixel coords), attributes, created/updated timestamps | P0 |
| S2 | Soft delete + audit trail (who created/edited/deleted what, when) | P1 |
| S3 | Optimistic concurrency: detect two users editing the same image (version number / etag); lock-on-open or conflict dialog | P1 |
| S4 | Annotation history per image (revisions, restore previous version) | P2 |
| S5 | Review workflow: *annotated → in review → approved / rejected (with comment)* | P1 |
| S6 | Multiple annotators per image + consensus/adjudication view (IoU-based agreement, disagreement highlighting) | P2 |
| S7 | Inter-annotator agreement metrics (IoU, Cohen's κ for labels) | P2 |
| S8 | Gold/honeypot images for quality control | P2 |

## 8. Export / Import

| ID | Feature | Pri |
|----|---------|-----|
| X1 | Export per experiment, filterable by status (e.g. only approved) | P0 |
| X2 | Formats: **YOLO** (txt + `data.yaml`), **COCO JSON**, **Pascal VOC XML**, **CSV/JSON**; classification: folder-per-class or CSV | P0 |
| X3 | Train/val/test split on export (ratio, stratified, seeded) | P1 |
| X4 | Export as downloadable ZIP, generated as background job; link when ready | P1 |
| X5 | Import existing annotations (YOLO/COCO/VOC) to seed or migrate; map classes | P1 |
| X6 | Export includes dataset manifest (experiment version, class list, hashes, export date in Jalali + ISO) for reproducibility | P1 |
| X7 | Integration with this repo's training scripts (`train_detector.py`, `train_classifier.py`) — export layout compatible with existing dataset format | P1 |

## 9. Search, Statistics & Reporting

| ID | Feature | Pri |
|----|---------|-----|
| R1 | Global search (images, experiments, users) | P2 |
| R2 | Per-experiment class distribution, boxes per image, box size histograms | P1 |
| R3 | Annotator productivity (images/hour, boxes/image) | P2 |
| R4 | Audit log viewer (Admin) with filters and Jalali date range | P1 |

## 10. Internationalization & UX

| ID | Feature | Pri |
|----|---------|-----|
| L1 | Persian (فارسی) and English UI; full **RTL** support and Vazirmatn (or similar) font | P0 |
| L2 | Persian/Latin digit toggle; Jalali/Gregorian toggle | P1 |
| L3 | Light/dark theme (dark is useful for spectrograms) | P1 |
| L4 | Responsive layout for list pages; workspace optimized for desktop | P1 |
| L5 | Accessibility basics: keyboard navigation, contrast, focus states | P2 |
| L6 | In-app help / onboarding tour, shortcut cheat-sheet | P2 |

## 11. Non-Functional Requirements

**Security**
- HTTPS only in production; secure/httpOnly/SameSite cookies; CSRF protection
- Input validation, upload sanitization (re-encode images, strip metadata, reject polyglots), path-traversal-safe storage (never use user-supplied filenames on disk)
- Per-endpoint authorization checks and tests; secrets via environment, never in repo
- Dependency scanning; security headers (CSP, HSTS)

**Performance & scale**
- Server-side pagination and indexed filters (upload date, status, experiment); no loading of full lists
- Thumbnails + lazily loaded full-size images; support for large spectrograms (e.g. 4000×2000+) via tiled/downscaled previews
- Annotation save payloads are small (only diffs/per-image)

**Storage**
- Images on object storage (S3/MinIO) or local volume behind an abstraction; metadata + annotations in PostgreSQL
- Original images immutable; derived thumbnails regenerable

**Reliability & operations**
- Docker Compose deployment (web, API, DB, storage, worker) — see `docker-compose.yml`
- Automated DB backups and migrations; background worker for thumbnails, exports, auto-labeling
- Structured logging, health endpoints, error monitoring
- Unit/integration tests for permissions, date conversion (Jalali ↔ UTC, incl. leap years and range boundaries), annotation CRUD, and export-format correctness

**Data integrity**
- Bounding boxes stored normalized (0–1) with image dimensions so they survive resizing; validated to lie inside the image
- Referential integrity: deleting a class/image/experiment cascades or is blocked per rules above

---

## 12. Additional Features Recommended (not in the original request)

1. **Annotation review/approval workflow** (S5) — essential for training-quality labels.
2. **Task assignment & progress tracking** (E12, E10) — splits work across annotators.
3. **Audit log** (S2, R4) — accountability and debugging.
4. **Export to YOLO/COCO/VOC** (X2) — the data is useless to the ML pipeline otherwise.
5. **Model-assisted pre-labeling** (W19) — large speed-up; reuse `yolo26s.pt` and the SAM auto-labeling work.
6. **Spectrogram metadata & physical-unit readout** (I14, W12) — boxes become time/frequency regions, not just pixels.
7. **Image-level "negative / no-signal" status** (W16) — needed for detector training.
8. **Duplicate detection** (I5) and **soft delete** (I13).
9. **Concurrency control** (S3) — prevents silent overwrites.
10. **Inter-annotator agreement + gold images** (S6–S8) — label quality measurement.
11. **Background jobs** for export / thumbnails / auto-label.
12. **Backups, logging, rate limiting, 2FA** (Section 11, A5, A7).

---

## 13. Suggested Data Model (high level)

```
User(id, username, email, password_hash, role, is_active, locale, calendar_pref, created_at)
Image(id, storage_key, thumb_key, filename_orig, sha256, width, height, size_bytes,
      uploaded_by→User, uploaded_at[UTC], metadata JSON, tags[], deleted_at)
Experiment(id, name, description, task_type, owner→User, status, settings JSON, created_at)
ExperimentMember(experiment→Experiment, user→User, role)
ClassDef(id, experiment→Experiment, scope{box|image}, name, color, hotkey, order, parent_id)
ExperimentImage(experiment→Experiment, image→Image, status, assigned_to→User, locked_by, version)
BoundingBox(id, experiment_image→ExperimentImage, class→ClassDef, x, y, w, h [normalized],
            attributes JSON, source{human|model}, created_by, created_at, updated_at, deleted_at)
ImageLabel(experiment_image, class→ClassDef, created_by, created_at)      -- classification
Review(id, experiment_image, reviewer, decision, comment, created_at)
AuditLog(id, user, action, entity, entity_id, diff JSON, at[UTC])
```

## 14. Suggested Delivery Phases

1. **MVP (P0):** auth + roles, user admin, upload + paginated library with Jalali date filter, experiments with class definitions, annotation workspace (draw/edit/delete/save, labels), YOLO/COCO export.
2. **Phase 2 (P1):** review workflow, assignment, dashboards, spectrogram unit readout, concurrency control, audit log, import, i18n polish.
3. **Phase 3 (P2):** model-assisted pre-labeling, consensus & agreement metrics, SSO/2FA, polygon/segmentation tasks.

## 15. Open Questions

- Expected scale: number of images, image resolution, number of concurrent annotators?
- Deployment: single on-prem machine (offline, no email) or cloud? Affects reset-password flow, storage choice and SSO.
- Do spectrograms carry physical metadata (sample rate, center frequency, window/hop) that should map pixels → Hz/seconds?
- Should one image belong to multiple experiments with independent annotations? (Current model: yes.)
- Is review mandatory, and is multi-annotator consensus required?
- Preferred stack — `backend-stack.md` and `frontend-stack.md` are currently empty; this spec is stack-agnostic.
