---
name: visiox-backend-agent
description: Enforces architecture, coding standards, and CVAT integration patterns for the VisioX Django REST backend. Use this skill whenever generating or modifying Python backend code.
---

# VisioX Backend Engineering Guidelines

When acting as an AI coding assistant on the VisioX backend repository, you MUST follow these architectural, integration, and coding rules. This is a Django REST Framework (DRF) API that serves as the central backend for the VisioX computer-vision platform, deeply integrated with a customized CVAT annotation service.

## 1. Core Tech Stack
- **Framework**: Django 6.0 with Django REST Framework 3.16
- **Authentication**: `djangorestframework-simplejwt` (JWT Bearer tokens). Access token lifetime: 1 hour, refresh: 7 days.
- **Database**: PostgreSQL 16 (shared with CVAT via Docker `shared_db` network)
- **Task Queue**: Celery 5.6 + Redis 7.2 + `django-celery-beat` for periodic tasks
- **CVAT SDK**: `cvat-sdk==2.25.0` for programmatic CVAT interaction
- **HTTP Client**: `requests` for direct CVAT REST API calls when SDK is insufficient
- **API Docs**: `drf-spectacular` (OpenAPI 3 schema at `/api/schema/`, Swagger at `/api/docs/`)
- **Profiling**: `django-silk` (available at `/silk/` in DEBUG mode)
- **Storage**: Local filesystem by default, S3 via `django-storages` + `boto3` when `USE_S3=True`

## 2. Project Structure (Django Apps)
```
visiox/
├── visiox/          # Project config (settings.py, urls.py, wsgi.py, celery.py)
├── core/            # Custom user model (UserModel), base permissions
├── authentication/  # Login, Register, Logout, Me (JWT), Token refresh
├── teams/           # Team model and CRUD
├── projects/        # Project model (with cvat_project_id), CRUD
├── datasets/        # Dataset + Media models, CVAT integration, webhook handler
│   ├── models.py        # Dataset (cvat_task_id), Media
│   ├── services/cvat.py # All CVAT SDK/API interactions (singleton client)
│   ├── views/           # DatasetViewSet, webhook_view
│   └── serializers/     # DatasetSerializer, MediaSerializer
├── annotations/     # Annotation-related endpoints
├── training/        # TrainingJob, ModelArchitecture, Experiment, RunMetric
├── deployments/     # ModelRegistry, InferenceEndpoint
├── billing/         # Stripe integration, API key auth
├── db/              # Database init scripts (init-cvat.sql)
└── scripts/         # Maintenance scripts (pull_missing_tasks, update_webhooks)
```

## 3. CVAT Integration Architecture

### 3.1 Service Layer (`datasets/services/cvat.py`)
ALL CVAT interactions MUST go through this centralized service module. Never call CVAT APIs directly from views.

**Client Management:**
- Thread-safe singleton pattern with `_client_lock` and `_cached_client`
- `get_cvat_client()` — lazily creates and caches the `cvat_sdk.Client`, sets `Host`/`Origin` headers for Docker routing
- `invalidate_client()` — forces re-authentication on next call
- `_authed_session()` — returns a `requests.Session` with basic auth for direct REST calls

**Key Functions:**
- `create_cvat_project(name, labels)` → project_id
- `create_cvat_task(project_id, name)` → task_id
- `upload_cvat_data(task_id, file_paths)` — batch upload (CVAT allows data upload only ONCE per task)
- `delete_cvat_task(task_id)` → bool
- `update_cvat_task(task_id, name=...)` — PATCH via REST
- `ensure_cvat_task(dataset)` — idempotent provisioning: creates project + task if missing, repairs orphans
- `cvat_task_exists(task_id)` → bool — health check
- `repair_orphaned_datasets()` — finds datasets with missing CVAT tasks and recreates them
- `register_cvat_webhook(cvat_project_id)` — registers webhook for task/job events
- `get_cvat_task_stats(task_id)` → dict — jobs, annotations, metadata
- `get_cvat_browser_data(task_id, project_id)` → dict — frames, labels, annotations for UI data browser
- `get_cvat_frame_image(task_id, frame_num, quality)` → (bytes, content_type) — image proxy

### 3.2 Dataset-CVAT Lifecycle
1. **Create**: `DatasetViewSet.perform_create` → `ensure_cvat_task()` auto-provisions CVAT project + task
2. **Update**: Name changes sync to CVAT via `update_cvat_task()`
3. **Delete**: `perform_destroy` deletes the CVAT task before the Django model
4. **Annotate**: `/datasets/{id}/annotate_url/` ensures task exists and returns CVAT URL
5. **Sync**: `/datasets/{id}/sync_cvat/` fetches metadata and bumps version
6. **Repair**: `/datasets/repair-cvat/` (POST) recreates missing CVAT tasks with re-uploaded media

### 3.3 Data Browser Endpoints
- `GET /api/datasets/{id}/browser/` — Returns frames, labels, and per-frame annotations for the UI data browser
- `GET /api/datasets/{id}/stats/` — Unified VisioX + CVAT statistics
- `GET /api/datasets/{id}/frames/{num}/?quality=compressed&token={jwt}` — Image proxy from CVAT
  - Uses `authentication_classes=[]` and `permission_classes=[AllowAny]` at DRF level
  - Manually validates JWT from `token` query parameter (required for `<img src>` tags)
  - Returns raw image bytes with `Cache-Control: public, max-age=3600`

### 3.4 Webhook Handler (`datasets/views/webhook_view.py`)
- Endpoint: `POST /api/datasets/cvat-webhook/`
- Receives CVAT project events: `create:task`, `update:task`, `update:job`, `delete:task`
- Auto-creates VisioX `Dataset` records when tasks are created in CVAT
- Links to `Project` via `cvat_project_id`

## 4. Authentication & SSO

### 4.1 VisioX Auth
- JWT-based via SimpleJWT: `POST /api/auth/login/` returns `{access_token, refresh_token}`
- `POST /api/auth/register/`, `POST /api/auth/logout/`, `POST /api/auth/token/refresh/`
- `GET /api/auth/me/` — returns authenticated user info (used by CVAT SSO)
- Secondary auth: `billing.backends.APIKeyAuthentication` for API key access

### 4.2 CVAT SSO Flow
CVAT validates VisioX JWTs by calling `GET {VISIOX_API_URL}/api/auth/me/` with the Bearer token. The VisioX `/me/` endpoint returns user info that CVAT uses to auto-provision/update a local user and establish a session.

## 5. Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | insecure default | Django secret key |
| `DEBUG` | `True` | Debug mode |
| `DATABASE_HOST` | `localhost` | PostgreSQL host (use `db` in Docker) |
| `DATABASE_NAME` | `visiox` | Database name |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Redis broker |
| `CVAT_HOST` | `http://localhost:8080` | CVAT internal URL (Docker: `http://cvat_server:8080`) |
| `CVAT_PUBLIC_URL` | `http://localhost:8080` | CVAT public-facing URL |
| `CVAT_USERNAME` | `admin` | CVAT service account username |
| `CVAT_PASSWORD` | `master123` | CVAT service account password |
| `CVAT_WEBHOOK_URL` | `http://host.docker.internal:8000/...` | Webhook callback URL |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Frontend origin |
| `USE_S3` | `False` | Enable S3 storage |

## 6. Docker Compose Services
- **`db`** (postgres:16-alpine) — shared with CVAT via `shared_db` network
- **`redis`** (redis:7.2) — Celery broker and result backend
- **`api`** — Django dev server on port 8000, connects to `cvat_cvat` network
- **`worker`** — Celery worker for async tasks
- **`beat`** — Celery beat scheduler

External networks: `shared_db` (database sharing), `cvat_cvat` (CVAT service communication).

## 7. Coding Standards
- **Logging**: Use `logging.getLogger(__name__)` — NEVER use `print()` for debugging. Use `logger.info()`, `logger.warning()`, `logger.exception()`.
- **Error handling**: Use `except Exception:` (never bare `except:`). Always log with `logger.exception()` for stack traces.
- **Imports**: Group as stdlib → Django → DRF → third-party → local apps. Use absolute imports.
- **Views**: Use DRF `ModelViewSet` with `@action` decorators for custom endpoints. Override `get_permissions()` for action-specific permissions.
- **Serializers**: Always pass `context={'request': request}` when manually instantiating serializers.
- **Models**: Use `select_related()` and `prefetch_related()` to avoid N+1 queries. Use `update_fields` in `.save()` calls.
- **CVAT service**: Always call functions from `datasets.services.cvat` — never instantiate `cvat_sdk.Client` elsewhere.

## 8. Multi-Repo Architecture
VisioX spans three repositories:
- **`visiox`** (this repo): Django REST backend — API, CVAT SDK, auth, task queue
- **`visiox-ui`**: Next.js 16 frontend — UI, data browser, annotation iframe
- **`cvat`**: Customized CVAT fork — SSO endpoint, VisioX branding, shared database

The backend acts as a bridge between the frontend and CVAT, proxying data and images while handling authentication and business logic.
