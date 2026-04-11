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
| `db` | 5432 | PostgreSQL (shared with CVAT) |
| `redis` | 6379 | Celery broker |

Networks: `shared_db` (database), `cvat_cvat` (CVAT services).
