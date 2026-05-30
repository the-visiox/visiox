# VisioX Backend — Agent Configuration

Django REST API backend for the VisioX computer-vision platform.  
Pairs with **visiox-ui** (Next.js) and the optional **cvat** fork in sibling repos.

---

## Quick Reference

| Topic | Detail |
|---|---|
| Dev server | `python manage.py runserver 0.0.0.0:8000` |
| API base URL | `http://localhost:8000/api/` |
| Swagger UI | `http://localhost:8000/api/docs/` |
| ReDoc | `http://localhost:8000/api/redoc/` |
| OpenAPI schema | `http://localhost:8000/api/schema/` |
| Django admin | `http://localhost:8000/admin/` |
| Silk profiler | `http://localhost:8000/silk/` (DEBUG=True only) |
| Demo account | `demo@visiox.ai` / `Demo1234!` |

---

## Three-Repo Architecture

```
visiox-ui/          ← Next.js frontend
    ↕ REST API (JWT Bearer / X-API-KEY)
visiox/             ← This repo — Django API, Celery, PostgreSQL, Redis
    ↕ cvat-sdk + REST
cvat/               ← Customized CVAT fork (annotation engine, optional)
```

---

## Runtime

### Start (3-terminal dev setup)

**Terminal A — Database + Redis:**
```bash
# inside visiox/
docker compose up -d db redis
```

**Terminal B — Django API:**
```bash
python manage.py migrate
python manage.py setup_groups
python manage.py seed_demo_data
python manage.py runserver 0.0.0.0:8000
```

**Terminal C — Celery workers (optional):**
```bash
celery -A visiox worker -l info
celery -A visiox beat -l info
```

### Full Docker stack
```bash
docker compose up --build -d
# then:
docker compose exec api python manage.py migrate
docker compose exec api python manage.py setup_groups
docker compose exec api python manage.py seed_demo_data
```

### Docker services
| Service | Port | Description |
|---|---|---|
| `db` | 5433 (host) / 5432 (internal) | PostgreSQL 16 |
| `redis` | 6379 | Redis 7 (Celery broker + results) |
| `api` | 8000 | Django API |
| `worker` | — | Celery worker |
| `beat` | — | Celery beat scheduler |

> **Host vs Docker DB:** When running `manage.py` on the host (not inside a container), use `DATABASE_HOST=localhost` and `DATABASE_PORT=5433`. Inside containers, use `DATABASE_HOST=db` and `DATABASE_PORT=5432`.

---

## Domain Apps

| App | Models | Responsibility |
|---|---|---|
| `core` | `UserModel` | Custom user (extends AbstractUser), permissions, JWT query-param auth |
| `authentication` | — | Login, register, logout, OAuth (Google/GitHub), token refresh |
| `teams` | `Team`, `TeamMember`, `Invitation` | Teams, member roles, email invitations |
| `projects` | `Project` | Project metadata, task type, CVAT project mapping |
| `datasets` | `Dataset`, `Media`, `MediaLabelProfile` | Dataset records, media upload, frame proxy, CVAT task mapping |
| `annotations` | `Class`, `Annotation`, `LabelingTask`, `JobIssue`, `Review` | Labels, annotations, jobs, QA, reviews, export |
| `training` | `ModelArchitecture`, `TrainingJob`, `Experiment`, `RunMetric` | Architecture catalog, training jobs, experiment metrics |
| `deployments` | `ModelRegistry`, `InferenceEndpoint`, `MonitoringLog`, `DriftAlert` | Model registry, inference endpoints, monitoring, drift detection |
| `billing` | `Plan`, `Subscription`, `UsageRecord`, `APIKey`, `Webhook` | Plans, Stripe subscriptions, usage, API keys, outbound webhooks |
| `dataverse` | `DataverseProject` | Public dataset hub, project sharing, forking |

---

## Key Integration Points

### JWT Authentication
- `djangorestframework-simplejwt` — access token (1h) + refresh token (7d)
- Auto-rotate refresh tokens; old refresh tokens are blacklisted on rotation
- Frame image endpoints (`/api/datasets/{id}/frames/{n}/`) dùng `AllowAny` — không cần auth
- `core/jwt_query_auth.py` định nghĩa `JWTAuthQueryOrHeader` (subclass hỗ trợ `?token=`) nhưng hiện **chưa được đăng ký** vào `DEFAULT_AUTHENTICATION_CLASSES`

### API Key Authentication
- Header: `X-API-KEY: <plain key>`
- Backed by `billing/backends.py` — validates SHA256 hash, updates `last_used`
- Create via `POST /api/api-keys/` — raw key shown **once only**

### CVAT (optional)
- Enabled by default; disabled with `VISIOX_STANDALONE=true`
- All integration in `datasets/services/cvat.py`
- CVAT webhook receiver at `POST /api/datasets/cvat-webhook/` (AllowAny)
- SSO-style annotation URL via `GET /api/datasets/{id}/annotate_url/`

### Celery Background Tasks
| Task | App | Trigger |
|---|---|---|
| `provision_cvat_task` | datasets | Dataset created |
| `run_training_job` | training | Job started |
| `check_endpoint_drift` | deployments | Periodic / manual trigger |
| `deliver_webhook` | deployments | Event fired |

### Stripe
- Webhook at `POST /api/webhooks/stripe/` (AllowAny, validates `Stripe-Signature`)
- Keys: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`

### Storage
- **Default:** local filesystem — `MEDIA_ROOT = BASE_DIR / 'media'`
- **S3:** enable with `USE_S3=true` + AWS env vars

---

## Environment Variables

### Required
| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | — | Django secret key |
| `DATABASE_NAME` | `visiox_db` | PostgreSQL DB name |
| `DATABASE_USER` | `postgres` | PostgreSQL user |
| `DATABASE_PASSWORD` | `postgres` | PostgreSQL password |
| `DATABASE_HOST` | `localhost` | PostgreSQL host |
| `DATABASE_PORT` | `5433` | PostgreSQL port (5433 Docker, 5432 native) |
| `CELERY_BROKER_URL` | `redis://127.0.0.1:6379/0` | Redis broker |
| `CELERY_RESULT_BACKEND` | `redis://127.0.0.1:6379/0` | Redis results |

### Optional — App Behavior
| Variable | Default | Description |
|---|---|---|
| `DEBUG` | `False` | Enable Django debug mode + Silk profiler |
| `ALLOWED_HOSTS` | `*` | Comma-separated allowed hosts |
| `CORS_ALLOWED_ORIGINS` | `localhost:3000,...` | Comma-separated CORS origins |
| `VISIOX_STANDALONE` | `false` | Disable CVAT; use VisioX-native annotation only |
| `TIME_ZONE` | `Asia/Ho_Chi_Minh` | Django/Celery timezone |

### Optional — CVAT
| Variable | Description |
|---|---|
| `CVAT_INTERNAL_HOST` | CVAT internal URL (default `http://localhost:8080`) |
| `CVAT_PUBLIC_URL` | CVAT public-facing URL |
| `CVAT_USERNAME` | CVAT admin username |
| `CVAT_PASSWORD` | CVAT admin password |
| `CVAT_WEBHOOK_URL` | URL CVAT posts webhook events to (default `http://host.docker.internal:8000/api/datasets/cvat-webhook/`) |

### Optional — OAuth
| Variable | Description |
|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth client secret |
| `GITHUB_OAUTH_CLIENT_ID` | GitHub OAuth client ID |
| `GITHUB_OAUTH_CLIENT_SECRET` | GitHub OAuth client secret |

### Optional — Storage
| Variable | Description |
|---|---|
| `USE_S3` | `true` to use S3 instead of local filesystem |
| `AWS_ACCESS_KEY_ID` | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key |
| `AWS_STORAGE_BUCKET_NAME` | S3 bucket name |
| `AWS_S3_REGION_NAME` | S3 region (default `us-east-1`) |

### Optional — Stripe
| Variable | Description |
|---|---|
| `STRIPE_SECRET_KEY` | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |

### Optional — Email
| Variable | Default | Description |
|---|---|---|
| `EMAIL_HOST` | — | SMTP host |
| `EMAIL_PORT` | `587` | SMTP port |
| `EMAIL_USE_TLS` | `True` | SMTP TLS |
| `EMAIL_HOST_USER` | — | SMTP user |
| `EMAIL_HOST_PASSWORD` | — | SMTP password |
| `DEFAULT_FROM_EMAIL` | `VisioX <noreply@visiox.ai>` | Sender address |

---

## Key Directories

```
visiox/                         # Django settings package
├── settings.py                 # All configuration (DB, JWT, Celery, CORS, CVAT, S3, Stripe)
├── urls.py                     # Root URL conf — mounts all app routers under /api/
├── celery.py                   # Celery app init
├── wsgi.py / asgi.py

core/                           # Custom user + shared utilities
├── models/user.py              # UserModel (AbstractUser)
├── permissions.py              # HasPerm(perm) permission factory
└── jwt_query_auth.py           # JWT from ?token= query param

authentication/                 # Auth endpoints
├── views/                      # login, register, logout, me, oauth
├── serializers/
└── services/auth_service.py, oauth_service.py

teams/                          # Team management
├── models.py                   # Team, TeamMember, Invitation
├── views/team_view.py          # TeamViewSet (CRUD + members + invitations)
├── email_service.py            # send_invitation_email()
└── permissions.py              # IsTeamOwnerOrAdmin

projects/                       # Project metadata
├── models.py                   # Project (task_type, cvat_project_id)
├── views/project_view.py       # ProjectViewSet
└── permissions.py              # IsProjectOwnerOrTeamAdmin

datasets/                       # Dataset + media
├── models.py                   # Dataset, Media, MediaLabelProfile
├── views/dataset_view.py       # DatasetViewSet (upload, browser, frames, sync)
├── views/webhook_view.py       # CVAT webhook receiver
├── services/cvat.py            # All CVAT operations (provision, proxy, sync, repair)
├── standalone.py               # Fallback when VISIOX_STANDALONE=true
└── tasks.py                    # provision_cvat_task (Celery)

annotations/                    # Annotation pipeline
├── models.py                   # Class, Annotation, LabelingTask, JobIssue, Review
├── views/class_view.py         # ClassViewSet
├── views/annotation_view.py    # AnnotationViewSet (bulk create/delete)
├── views/task_view.py          # LabelingTaskViewSet (job lifecycle + issues)
├── views/review_view.py        # ReviewViewSet
├── views/label_profile_view.py # Media + frame label profiles
├── views/export_view.py        # DatasetExportView (COCO/YOLO/VOC)
└── views/quality_view.py       # Annotation QA metrics

training/                       # Model training
├── models.py                   # ModelArchitecture, TrainingJob, Experiment, RunMetric
├── views/training_view.py      # ViewSets for all training resources
└── tasks.py                    # run_training_job (Celery)

deployments/                    # Model deployment
├── models.py                   # ModelRegistry, InferenceEndpoint, MonitoringLog, DriftAlert
├── views/deployment_view.py    # ViewSets for all deployment resources
└── tasks.py                    # check_endpoint_drift, deliver_webhook (Celery)

billing/                        # Billing & API keys
├── models.py                   # Plan, Subscription, UsageRecord, APIKey, Webhook
├── views/billing_view.py       # ViewSets + StripeWebhookView
└── backends.py                 # APIKeyAuthentication (X-API-KEY header)

dataverse/                      # Public dataset hub
├── models.py                   # DataverseProject
└── views/dataverse_view.py     # DataverseProjectViewSet (share, fork)

scripts/                        # Utility scripts
├── seed_test_data.py
├── pull_missing_tasks.py
└── check_auth.py

docs/                           # Documentation
├── API.md                      # Full API reference
├── ARCHITECTURE_DIAGRAMS.md    # System + data flow diagrams
└── ROADMAP.md                  # Feature roadmap
```

---

## Useful Commands

```bash
# Dev
python manage.py runserver 0.0.0.0:8000
python manage.py migrate
python manage.py makemigrations
python manage.py showmigrations datasets
python manage.py setup_groups
python manage.py seed_demo_data

# Celery
celery -A visiox worker -l info
celery -A visiox beat -l info

# CVAT sync
python scripts/pull_missing_tasks.py
```

---

## Testing Rule

- After creating or changing functionality, run the most relevant verification before finishing.
- For backend changes: `python manage.py test <app_or_test_case>` (narrow first, expand when needed).
- When the change affects routing, settings, migrations, or shared services, run broader verification.
- Do not claim a feature is done without reporting which command was run and whether it passed.
- If a test cannot run due to missing services, state the blocker clearly.

---

## API Surface Summary

| Domain | Endpoint prefix | ~Endpoints |
|---|---|---|
| Auth | `/api/auth/` | 6 |
| Teams | `/api/teams/`, `/api/invitations/` | 11 |
| Projects | `/api/projects/` | 5 |
| Datasets | `/api/datasets/` | 13 |
| Annotations | `/api/classes/`, `/api/annotations/`, `/api/tasks/`, `/api/jobs/`, `/api/reviews/` | 20+ |
| Training | `/api/architectures/`, `/api/training-jobs/`, `/api/experiments/` | 8 |
| Deployments | `/api/registry/`, `/api/endpoints/`, `/api/monitoring/`, `/api/drift-alerts/` | 10 |
| Billing | `/api/plans/`, `/api/subscriptions/`, `/api/usage/`, `/api/api-keys/`, `/api/webhooks/` | 10 |
| Dataverse | `/api/dataverse/` | 4 |
| Docs | `/api/schema/`, `/api/docs/`, `/api/redoc/` | 3 |

Full reference: [`docs/API.md`](./docs/API.md)  
Architecture diagrams: [`docs/ARCHITECTURE_DIAGRAMS.md`](./docs/ARCHITECTURE_DIAGRAMS.md)
