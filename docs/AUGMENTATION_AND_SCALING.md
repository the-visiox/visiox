# Dataset Background Work and Scaling

This document covers dataset imports, augmentation, thumbnails and the current
Celery layout. For deployment commands, see
[DEPLOY_DATASET_WORKER_MINIO.md](DEPLOY_DATASET_WORKER_MINIO.md).

## Current topology

| Worker | Host | Queue | Concurrency | Prefetch | Purpose |
| --- | --- | --- | ---: | ---: | --- |
| `general-worker@...` | `.9` | `celery` | 2 | 1 | Augmentation, label-cache work, training orchestration, drift and webhooks |
| `dataset-worker@...` | `.20` | `datasets` | 1 | 1 | Dataset import processing close to MinIO |
| GPU worker | GPU host | `gpu_training` | Deployment-specific | Deployment-specific | GPU execution outside the Django worker |

Both Django workers run as `uid=10001(visiox)` using `Dockerfile.worker`.
Celery hostnames include a container ID and change after recreation; inspect
queues without hardcoding a hostname.

## Required migrations

Run migrations after pulling model changes:

```bash
python manage.py migrate
python manage.py showmigrations datasets
```

Important dataset migrations include:

- `0010_augmentationjob`: persistent augmentation progress
- `0011_media_thumbnail`: precomputed thumbnails
- `0014_datasetimportjob`: queued/running/done/error import state

The API container runs `python manage.py migrate --noinput` at startup. The
dataset worker must use the same source revision and database schema as the API.

## Dataset import flow

```text
Browser -> Django API (.9)
  -> create DatasetImportJob(status=queued)
  -> stage upload in default storage
  -> publish process_dataset_import_task to queue datasets
  -> dataset-worker (.20) reads staging from MinIO
  -> validate archive / create media in batches / update progress
  -> cleanup staging
  -> status done or error
```

Only `process_dataset_import_task` is explicitly routed to `datasets` in the
current source. Other dataset tasks using `.delay()` remain on the default
`celery` queue and are handled by the general worker.

Supported imports are images, YOLO26 ZIP and COCO. A YOLO26 archive must contain
`data.yaml`; otherwise the job ends in `error` with the message persisted for
the UI.

Performance settings:

```env
USE_CELERY=True
DATASET_IMPORT_STORAGE_WORKERS=6
DATASET_IMPORT_BATCH_SIZE=24
```

`DATASET_IMPORT_STORAGE_WORKERS` bounds parallel object-storage I/O inside one
import. `DATASET_IMPORT_BATCH_SIZE` bounds batch database writes and progress
updates. Keep dataset-worker Celery concurrency at `1` unless load tests show
the MinIO host can sustain multiple simultaneous archives.

## Augmentation flow

```text
POST /api/v1/datasets/{id}/augmentations/
  -> create AugmentationJob(status=running)
  -> USE_CELERY=True: augment_dataset_task.delay(...) -> queue celery
  -> USE_CELERY=False: daemon thread for development only
  -> return 202 with job_id

GET /api/v1/datasets/{id}/augmentations/status/?job={id}
  -> read persisted total/done/generated/status/error
```

The image and its annotations pass through the same Albumentations pipeline.
Bounding boxes, polygons and keypoints are transformed with the image, and the
label profile is copied to generated media.

Key implementation files:

- `datasets/views/dataset_view.py`
- `datasets/tasks.py`
- `datasets/models.py`

## Thumbnails

- `GET /api/v1/datasets/{id}/frames/{n}/?quality=thumb` serves the precomputed
  `media.thumbnail`.
- `quality=compressed` serves full image bytes for annotation work.
- `quality=original` serves the original object.
- Legacy media gets a thumbnail lazily on first request.
- New and augmented images create thumbnails during processing.

This avoids repeatedly decoding large originals for gallery views.

Before adding a CDN, preserve authorization semantics. Ignoring JWT query
parameters in a cache key is safe only when the cached object is otherwise
protected from cross-tenant access.

## Environment by host

API and general worker on `.9` use LAN endpoints:

```env
DATABASE_HOST=10.29.30.20
DATABASE_PORT=5432
CELERY_BROKER_URL=redis://10.29.30.20:6379/0
CELERY_RESULT_BACKEND=redis://10.29.30.20:6379/0
MINIO_ENDPOINT=http://10.29.30.20:9000
```

Dataset worker on `.20` uses Compose DNS:

```env
DATABASE_HOST=db
DATABASE_PORT=5432
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
MINIO_ENDPOINT=http://minio:9000
```

## Operations

Inspect queues from `.20`:

```bash
docker compose -p infiniq -f docker-compose.infra.yml exec -T worker-datasets \
  celery -A visiox inspect active_queues
```

Inspect active tasks before maintenance:

```bash
docker compose -p infiniq -f docker-compose.infra.yml exec -T worker-datasets \
  celery -A visiox inspect active
```

Recreate only the dataset worker:

```bash
docker compose -p infiniq -f docker-compose.infra.yml up -d \
  --no-deps --force-recreate worker-datasets
```

On `.9`:

```bash
docker compose exec -T worker celery -A visiox inspect active_queues
docker compose logs -f worker
```

## Scaling guidance

Already implemented:

- Persistent import and augmentation progress in PostgreSQL
- Precomputed thumbnails
- Dedicated dataset import queue near MinIO
- Bounded storage thread pool and batch database writes
- Separate general, dataset and GPU queues
- Non-root worker images

Next priorities:

1. Add monitoring for queue depth, task duration, failures and MinIO latency.
2. Put PgBouncer in front of PostgreSQL before increasing API replicas.
3. Back up PostgreSQL and `/data/minio` and test restore procedures.
4. Add a CDN only with tenant-safe authorization/cache rules.
5. Move PostgreSQL, Redis and object storage to independent or managed services
   before high availability is required.

Current limitation: PostgreSQL, Redis, MinIO and the dataset worker share `.20`.
This reduces import latency but remains a single-host failure domain and creates
resource contention during large imports.
