# Augmentation Pipeline, Thumbnails & Scaling

How dataset augmentation, gallery thumbnails, and background jobs work — and how
to run/scale them. Read the **Migrations** section first if the dataset detail
page suddenly shows `0 images` after a code update.

---

## ⚠️ Migrations — run this after pulling model changes

Symptom: dataset page shows **0 Total Images / 0 Annotations / "No images or
videos yet"**, and `/stats`, `/browser`, `/media` return **500**.

Cause: the code (ORM) expects a new column/table that the database does not have
yet (e.g. `media.thumbnail`, `augmentation_jobs`). **No data is lost** — every
`SELECT * FROM media` just fails because the column is missing.

Fix — apply the migrations:

```bash
python manage.py migrate datasets
```

This is **additive DDL** (CREATE TABLE / ADD COLUMN) — it never deletes rows.
After it runs:

- `augmentation_jobs` table is created.
- `media.thumbnail` column is added (NULL for existing rows).
- Media endpoints stop 500-ing → existing images reappear.
- Thumbnails for old images are built lazily on first gallery view.

**Docker:** the `api` service runs `python manage.py migrate --noinput` on
startup, so `docker compose up` (or restarting `api`) applies them automatically.

> **Rule:** any change to a Django **model** requires a migration. Workflow on
> deploy/pull: `pull code → migrate → run app`.

---

## What changed (data model)

| Table / column | Purpose |
| --- | --- |
| `augmentation_jobs` | Tracks one augmentation run: `total / done / generated / status / error`, with `updated_at` as a heartbeat. Shared across all web workers; survives restarts. |
| `media.thumbnail` | Precomputed gallery thumbnail (FileField), stored under `…/{category}/thumbs/`. |

Migrations: `datasets/0010_augmentationjob.py`, `datasets/0011_media_thumbnail.py`.

---

## Augmentation flow

```
POST /api/v1/datasets/{id}/augmentations/   (preprocess, augment, multiplier)
  └─ create AugmentationJob(status=running, total=N)
  └─ dispatch work:
        USE_CELERY=True  → Celery task  augment_dataset_task   (worker process)
        USE_CELERY=False → background thread                    (dev server)
  └─ return 202 { job_id, total }   ← returns immediately

GET  /api/v1/datasets/{id}/augmentations/status/?job={id}
  └─ reads AugmentationJob row  → { total, done, generated, status, error }
  └─ self-heals: a 'running' job with no heartbeat for >300s is marked 'error'
```

The frontend (`DatasetDetailClient`) polls `status` and shows a non-blocking
progress card; the job runs in the background so the user is not blocked.

**Labels follow the image.** Each augmented copy is produced by running the image
**and its annotations** through one Albumentations pipeline (`bbox_params` +
`keypoint_params`), so boxes/polygons/points are transformed with the image.
Annotations and the per-image label profile are copied to the augmented media —
augmented images carry the same labels as their origin.

Key code: `datasets/views/dataset_view.py`
- `_augment_dataset(...)` — core loop (image + annotation transform, thumbnail).
- `run_augmentation_job(...)` — wraps it, writes progress to the job row.
- `datasets/tasks.py::augment_dataset_task` — Celery entry point.

---

## Thumbnails (gallery performance)

- Endpoint: `GET /frames/{n}/?quality=thumb` (also `compressed` = full bytes for
  the annotation canvas, `original`).
- `quality=thumb` serves the **precomputed** `media.thumbnail` straight from
  storage (no decode, CDN-cacheable, `Cache-Control: max-age=86400`).
- If a thumbnail is missing (legacy media), it is built **once** (~400px JPEG),
  saved to storage, then served — subsequent requests hit the fast path.
- Augmented images get their thumbnail at creation time.

This removes per-request CPU for gallery views.

### Putting a CDN in front (optional, for scale)
The thumbnail URL carries `?token=…` (per-session JWT), so a naive CDN keys each
token separately. Two options:
1. Configure the CDN to **ignore the `token` query param** in the cache key for
   the thumbnail route (thumbnails are identical regardless of user).
2. Expose thumbnails as **public** objects on MinIO/S3 and serve the storage/CDN
   URL directly (no token). Acceptable if downscaled previews are not sensitive.

---

## Configuration (`.env`)

Current infra: MinIO, PostgreSQL, Redis all on `10.29.30.20`.

```ini
# Postgres
DATABASE_HOST=10.29.30.20
DATABASE_PORT=5432
DATABASE_CONN_MAX_AGE=60        # persistent connections (use PgBouncer at scale)

# Redis / Celery
CELERY_BROKER_URL=redis://10.29.30.20:6379/0
CELERY_RESULT_BACKEND=redis://10.29.30.20:6379/0
USE_CELERY=True                 # True → Celery worker; False → background thread (dev)

# MinIO
USE_MINIO=True
MINIO_ENDPOINT=http://10.29.30.20:9000
```

### Running
- **Dev (simple):** `USE_CELERY=False` → augmentation runs in a daemon thread;
  progress still goes through the DB.
- **Production:** `USE_CELERY=True` + run a worker next to the web process:
  ```bash
  celery -A visiox worker -l info
  ```
  In Docker this is the `worker` service in `docker-compose.yml`.

---

## Scaling roadmap (target: ~10k users)

Principle: **stateless web + offload heavy work to workers + managed services +
auto-scaling container platform**. Keep the Django modular monolith.

| Stage | What | Why |
| --- | --- | --- |
| ✅ Done | Job/progress in DB (`augmentation_jobs`), not RAM | Works across many web workers; survives restarts |
| ✅ Done | Celery-ready augmentation (`USE_CELERY`) | Heavy work off the web request path |
| ✅ Done | Precomputed thumbnails | Removes per-request CPU for gallery |
| ✅ Done | DB `CONN_MAX_AGE` | Reuse connections across requests |
| Next | CDN in front of image/thumbnail endpoint | Offload image bandwidth |
| Next | Managed Postgres + **PgBouncer**, managed Redis | Avoid SPOF, pool connections |
| Next | Run web (gunicorn) + Celery workers on an **auto-scale container platform** (Cloud Run / Azure Container Apps / Render) | Scale each tier independently without managing K8s |
| Later | Object storage with lifecycle + CDN; read replicas | Throughput / cost |

**Not needed at this scale:** Kafka (this is a *task queue* problem → Celery, not
event streaming) and self-managed Kubernetes (managed container platforms suffice
to well beyond 10k). Microservices are unnecessary — keep the monolith.

### Current limitation
MinIO + PostgreSQL + Redis all run on a **single host (`10.29.30.20`)** → single
point of failure and shared-resource contention. Fine for dev/staging and a few
hundred users; split/upgrade to managed services before pushing toward 10k.

### Known follow-ups
- Stale-job detection is lazy (checked when the client polls `status`). A periodic
  cleanup (Celery beat) could mark abandoned jobs even without a poller.
- `media-fallback` gallery path (non-native datasets) still uses full `file_url`;
  could expose a `thumbnail_url` in `MediaSerializer` for CDN delivery.
