# VisioX Backend

Django REST API for the VisioX computer-vision platform. The backend manages
authentication, projects, datasets, annotations, training orchestration,
deployments and billing. The frontend lives in the sibling `visiox-ui` repo.

## Current deployment

| Host | Services | Notes |
| --- | --- | --- |
| `10.29.30.9` | Django API `:8000`, Celery beat, `general-worker` | General worker listens only to `celery`, concurrency `2`, prefetch `1` |
| `10.29.30.20` | PostgreSQL `:5432`, Redis `:6379`, MinIO `:9000/:9001`, `dataset-worker` | Dataset worker listens only to `datasets`, concurrency `1`, prefetch `1` |
| GPU host | Training/inference agents and GPU Celery worker | GPU worker listens only to `gpu_training` |

Both backend workers are built with `Dockerfile.worker` and run as
`uid=10001(visiox)`. Infrastructure on `.20` belongs to the Compose project
`infiniq`; include `-p infiniq` in commands unless the compose file declares
`name: infiniq`.

```text
visiox-ui -> Django API (.9) -> PostgreSQL / Redis / MinIO (.20)
                               -> celery queue   -> general-worker (.9)
                               -> datasets queue -> dataset-worker (.20)
                               -> GPU agent      -> GPU runtime
```

Container IDs and Celery node suffixes change after recreation. Do not hardcode
values such as `dataset-worker@<container-id>` in runbooks.

## Requirements

- Python 3.12+
- PostgreSQL 16+
- Redis 7+
- MinIO when `USE_MINIO=True`
- Docker Engine/Desktop with Docker Compose v2 for container deployment

## Environment setup

Create a local environment file and replace every placeholder:

```bash
cp env.example .env
```

The dataset worker on `.20` uses a separate template:

```bash
cp env.worker.example .env.worker
chmod 600 .env.worker
```

Never commit `.env`, `.env.worker`, database passwords, Django `SECRET_KEY`,
MinIO credentials or agent tokens. Use a MinIO service account rather than the
root account.

The current shared-service endpoints are:

```env
DATABASE_HOST=10.29.30.20
DATABASE_PORT=5432
CELERY_BROKER_URL=redis://10.29.30.20:6379/0
CELERY_RESULT_BACKEND=redis://10.29.30.20:6379/0
USE_MINIO=True
MINIO_ENDPOINT=http://10.29.30.20:9000
MINIO_BUCKET=visiox-media
```

Use `db`, `redis` and `minio` instead of IP addresses only from containers on
the `.20` Compose network.

## Run the API locally

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
# source .venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py setup_groups
python manage.py runserver 0.0.0.0:8000
```

Optional demo data:

```bash
python manage.py seed_demo_data
```

Useful URLs:

- API base: `http://localhost:8000/api/v1/`
- Swagger: `http://localhost:8000/api/docs/`
- ReDoc: `http://localhost:8000/api/redoc/`
- OpenAPI schema: `http://localhost:8000/api/schema/`
- Admin: `http://localhost:8000/admin/`

All application endpoints use `/api/v1/`. Documentation endpoints intentionally
remain under `/api/`.

## Run application services on `.9`

`docker-compose.yml` runs the API, general worker and beat. It connects to the
shared infrastructure on `.20` using `.env`.

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs -f worker
```

The general worker command is equivalent to:

```bash
celery -A visiox worker -l info \
  -Q celery \
  --concurrency=2 \
  --prefetch-multiplier=1 \
  --hostname=general-worker@%h
```

## Manage infrastructure and dataset worker on `.20`

Use the existing Compose project name so commands target the running stack:

```bash
docker compose -p infiniq -f docker-compose.infra.yml ps
docker compose -p infiniq -f docker-compose.infra.yml logs -f worker-datasets
docker compose -p infiniq -f docker-compose.infra.yml exec -T worker-datasets id
```

Expected worker identity:

```text
uid=10001(visiox) gid=10001(visiox)
```

Before recreating a worker, confirm it has no active task:

```bash
docker compose -p infiniq -f docker-compose.infra.yml exec -T worker-datasets \
  celery -A visiox inspect active
```

Then rebuild and recreate only the dataset worker. Do not restart PostgreSQL,
Redis or MinIO:

```bash
docker compose -p infiniq -f docker-compose.infra.yml build worker-datasets
docker compose -p infiniq -f docker-compose.infra.yml up -d \
  --no-deps --force-recreate worker-datasets
```

Inspect all queues without a hardcoded Celery hostname:

```bash
docker compose -p infiniq -f docker-compose.infra.yml exec -T worker-datasets \
  celery -A visiox inspect active_queues
```

Expected routing:

- `general-worker@...` -> `celery`
- `dataset-worker@...` -> `datasets`
- GPU worker -> `gpu_training`

## Dataset imports

With `USE_CELERY=True`, dataset import jobs are published explicitly to the
`datasets` queue and processed on `.20`, close to MinIO. The API stages incoming
files in the configured default storage and records progress in
`dataset_import_jobs`. Images, YOLO26 ZIP and COCO imports are supported.

YOLO26 archives must contain `data.yaml`; the file may be inside one top-level
directory. The upload dialog can safely update same-name YOLO26 images: existing
MinIO objects are reused, annotations are replaced after validation, and
unambiguous one-based label IDs are normalized to the class order in `data.yaml`.
Import failures are persisted on the job and should be displayed by
the frontend rather than remaining at “Upload queued for worker”.

Performance controls:

```env
DATASET_IMPORT_STORAGE_WORKERS=6
DATASET_IMPORT_BATCH_SIZE=24
```

Restart only `worker-datasets` after changing these values.

## Storage

- PostgreSQL is the source of truth for metadata, annotations and split state.
- `visiox-media` stores dataset media, thumbnails, import staging and generated
  label snapshots when MinIO delivery is enabled.
- `visiox-artifacts` stores model weights and training artifacts.
- MinIO credentials must never be sent to the browser.

See [docs/STORAGE.md](docs/STORAGE.md) for object paths and
[docs/DEPLOY_DATASET_WORKER_MINIO.md](docs/DEPLOY_DATASET_WORKER_MINIO.md) for
the deployment runbook.

## Verification

```bash
python manage.py check
python manage.py showmigrations datasets
python manage.py test datasets.tests
```

For documentation and Compose edits:

```bash
docker compose config --quiet
docker compose -p infiniq -f docker-compose.infra.yml config --quiet
```

The second command must run on `.20` where `.env.worker` exists.

## Documentation

- [API reference](docs/API.md)
- [Architecture diagrams](docs/ARCHITECTURE_DIAGRAMS.md)
- [Database schema](docs/DATABASE.md)
- [MinIO storage](docs/STORAGE.md)
- [Dataset worker deployment](docs/DEPLOY_DATASET_WORKER_MINIO.md)
- [Augmentation and scaling](docs/AUGMENTATION_AND_SCALING.md)
- [Training and GPU agent](docs/TRAIN.md)
- [Roadmap](docs/ROADMAP.md)

## Frontend pairing

The Next.js frontend uses `NEXT_PUBLIC_API_URL` without a trailing slash, for
example `http://10.29.30.9:8000`. It authenticates against
`/api/v1/auth/login/` and sends JWT Bearer tokens to `/api/v1/` endpoints.
