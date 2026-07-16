# VisioX Backend — Agent Guide

Django REST backend for VisioX. It pairs with the sibling Next.js repository
`visiox-ui`; the customized `cvat` repository is optional.

## Quick reference

| Item | Value |
| --- | --- |
| Development API | `python manage.py runserver 0.0.0.0:8000` |
| API prefix | `/api/v1/` |
| Swagger | `/api/docs/` |
| OpenAPI schema | `/api/schema/` |
| Django admin | `/admin/` |
| Tests | `python manage.py test <app_or_test_case>` |

Do not add credentials, `.env` values, access tokens or production secrets to
source or documentation. Use placeholders and scoped MinIO service accounts.

## Runtime topology

| Host | Services |
| --- | --- |
| `10.29.30.9` | Django API, Celery beat, `general-worker` on `celery` |
| `10.29.30.20` | PostgreSQL, Redis, MinIO, `dataset-worker` on `datasets` |
| GPU host | Training/inference agents and worker on `gpu_training` |

The `.20` stack uses Compose project `infiniq`; include `-p infiniq` in its
management commands. Celery node suffixes are dynamic container IDs and must not
be hardcoded. Both Django workers use `Dockerfile.worker` and run as
`uid=10001(visiox)`.

## Architecture

```text
visiox-ui -> Django REST API -> PostgreSQL
                            -> Redis -> celery workers
                            -> MinIO
                            -> GPU training/inference agents
```

Main Django apps:

- `authentication`, `core`: users, JWT and OAuth.
- `teams`, `projects`: ownership and collaboration.
- `datasets`, `annotations`: media, imports, classes and labeling workflows.
- `training`: architectures, jobs, experiments and metrics.
- `deployments`: model registry, inference and monitoring.
- `billing`, `dataverse`: subscriptions, API keys and shared datasets.

Detailed diagrams, database tables and REST contracts live under [docs/](docs/).
Do not duplicate those references here.

## Integration rules

### Authentication

- REST endpoints use SimpleJWT bearer authentication by default.
- `JWTAuthQueryOrHeader` is enabled only on frame-image endpoints that must work
  in browser image elements; do not enable query tokens globally.
- API keys use `X-API-KEY`; raw keys are returned only when created.

### Dataset storage and queues

- PostgreSQL is authoritative for metadata, annotations and split state.
- Local filesystem is the development default; shared deployments use MinIO
  with `USE_MINIO=True`.
- Dataset imports must be sent explicitly to `datasets`.
- General augmentation and label-cache tasks use `celery`.
- Training execution uses the configured GPU workflow/queue.
- Never expose MinIO credentials to the frontend.

### CVAT

- CVAT integration is isolated in `datasets/services/cvat.py`.
- Set `VISIOX_STANDALONE=true` for native annotation without CVAT.
- Preserve standalone behavior when changing dataset or annotation flows.

## Environment configuration

Use `env.example` for the API/general worker and `env.worker.example` for the
dataset worker. Important groups are:

- Django: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`.
- PostgreSQL: `DATABASE_*`.
- Celery: `USE_CELERY`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`.
- MinIO: `USE_MINIO`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`,
  `MINIO_SECRET_KEY`, `MINIO_BUCKET`.
- Dataset import: `DATASET_IMPORT_STORAGE_WORKERS`,
  `DATASET_IMPORT_BATCH_SIZE`.
- GPU agents: `TRAINING_*`, `INFERENCE_*`.
- Optional integrations: `CVAT_*`, OAuth, Stripe and email variables.

The templates and settings module are canonical; update them together when a
new environment variable is introduced.

## Common commands

```bash
python manage.py migrate
python manage.py setup_groups
python manage.py runserver 0.0.0.0:8000

docker compose config --quiet
docker compose up -d --build

docker compose -p infiniq -f docker-compose.infra.yml ps
docker compose -p infiniq -f docker-compose.infra.yml logs -f worker-datasets
```

See [docs/DEPLOY_DATASET_WORKER_MINIO.md](docs/DEPLOY_DATASET_WORKER_MINIO.md)
before rebuilding or recreating the remote dataset worker.

## Change rules

- Preserve existing migrations; create a new migration for schema changes.
- Keep API behavior backward compatible unless the task explicitly changes the
  contract.
- Queue long-running object-storage or ML work instead of blocking requests.
- Keep storage operations compatible with both local files and MinIO.
- Update the relevant document rather than copying the same information into
  several Markdown files.
- Prefer narrow, relevant tests first. Run broader checks for shared settings,
  routing, migrations or services.
- Report the verification command and result. If required infrastructure is
  unavailable, report that limitation explicitly.

## Documentation map

- [README.md](README.md): setup and entry points.
- [docs/API.md](docs/API.md): REST API reference.
- [docs/ARCHITECTURE_DIAGRAMS.md](docs/ARCHITECTURE_DIAGRAMS.md): system flows.
- [docs/DATABASE.md](docs/DATABASE.md): database schema.
- [docs/STORAGE.md](docs/STORAGE.md): MinIO policy and paths.
- [docs/AUGMENTATION_AND_SCALING.md](docs/AUGMENTATION_AND_SCALING.md): background dataset work.
- [docs/TRAIN.md](docs/TRAIN.md): training and inference agent contracts.
- [docs/DEPLOY_DATASET_WORKER_MINIO.md](docs/DEPLOY_DATASET_WORKER_MINIO.md): `.20` runbook.
