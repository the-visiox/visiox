# VisioX Backend — Agent Configuration

This is the **Django REST backend** for the VisioX computer-vision platform. It provides the API layer, manages CVAT integration, handles authentication, and orchestrates async tasks.

## Quick Reference

| Aspect | Detail |
|--------|--------|
| Framework | Django 6.0, DRF 3.16 |
| Auth | SimpleJWT (Bearer tokens) |
| Database | PostgreSQL 16 (shared with CVAT) |
| Task queue | Celery 5.6 + Redis 7.2 |
| CVAT SDK | cvat-sdk 2.25.0 |
| Dev server | `python manage.py runserver 0.0.0.0:8000` |
| Docker | `docker compose up -d` |
| Python (local) | 3.12+; Conda env example: `conda activate py312` |

## Local development (without the `api` container)

1. Copy `env.example` → `.env` and set `DATABASE_*`, `CELERY_*` to match your Postgres and Redis.
2. **Docker DB/Redis only** (common on dev machines): `docker compose up -d db redis` then run Django on the host with the same `.env`.
3. **Windows + Docker Postgres on the same machine**: if a **native PostgreSQL** install is already bound to `127.0.0.1:5432`, Django will talk to that instance first—not the container. Either stop the local service or map Docker’s DB to another host port and point Django at it:
   - In `.env`: set `DB_HOST_PORT=5433` (compose host mapping) and `DATABASE_PORT=5433` (what Django/psycopg2 uses when `DATABASE_HOST=127.0.0.1`).
   - Recreate the `db` container after changing `DB_HOST_PORT` so the new mapping applies.
4. Default DB credentials in `env.example` / typical local compose: user `postgres`, password `postgres`, database name from `DATABASE_NAME` (e.g. `visiox_db`). Change these in production.

Example host-only API after DB is reachable:

```bash
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

## Architecture

```
visiox-ui/                  ← Next.js frontend
  ↕ REST API (JWT)
visiox/                     ← This repo (Django backend)
  ↕ cvat-sdk + REST API
cvat/                       ← Customized CVAT fork (annotation engine)
```

### Key Integration Points

1. **CVAT Service** (`datasets/services/cvat.py`): Thread-safe singleton client, all CVAT SDK/REST calls centralized here.
2. **Dataset-CVAT Lifecycle**: Auto-provisions CVAT projects/tasks on dataset creation, syncs names, repairs orphans.
3. **Image Proxy**: `/api/datasets/{id}/frames/{num}/` proxies images from CVAT with JWT-via-query-param auth.
4. **Data Browser API**: `/api/datasets/{id}/browser/` aggregates frames, labels, and annotations from CVAT.
5. **SSO Support**: `/api/auth/me/` endpoint validates JWTs for CVAT's SSO flow.
6. **Webhooks**: `/api/datasets/cvat-webhook/` receives CVAT project events.

## Skills

- **`visiox-backend-agent`**: Django architecture, CVAT integration, coding standards

## Key Directories

```
visiox/                 # Project config (settings.py, urls.py, celery.py)
core/                   # Custom user model, base permissions
authentication/         # JWT login/register/logout/me
teams/                  # Team CRUD
projects/               # Project model (cvat_project_id)
datasets/               # Dataset + Media, CVAT integration hub
├── services/cvat.py    # All CVAT SDK/API interactions
├── views/              # DatasetViewSet, webhook handler
├── models.py           # Dataset (cvat_task_id), Media
└── serializers/        # DRF serializers
annotations/            # Annotation endpoints
training/               # TrainingJob, Experiment, Metrics
deployments/            # ModelRegistry, InferenceEndpoint
billing/                # Stripe, API keys
```

## Docker Services

| Service | Port | Description |
|---------|------|-------------|
| `api` | 8000 | Django dev server |
| `worker` | — | Celery worker |
| `beat` | — | Celery beat scheduler |
| `db` | `${DB_HOST_PORT:-5432}` → `5432` in container | PostgreSQL (host port configurable in `.env`; container always listens on `5432`) |
| `redis` | 6379 | Celery broker |

Networks: `shared_db` (database), `cvat_cvat` (CVAT services).

When the stack runs **only** `db` + `redis`, set `DATABASE_HOST=127.0.0.1` (or `localhost`) and `DATABASE_PORT` to the **published** host port so Django on the host reaches the container.
