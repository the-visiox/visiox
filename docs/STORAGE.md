# VisioX MinIO Storage

## Runtime topology

MinIO runs on `10.29.30.20`:

- S3-compatible API: `http://10.29.30.20:9000`
- Administration console: `http://10.29.30.20:9001`
- Container-network endpoint on `.20`: `http://minio:9000`

The Django API on `.9` reaches MinIO over the LAN. The dedicated dataset worker
runs on `.20` and uses the Docker-network endpoint, avoiding an extra LAN hop
while importing archives and images.

PostgreSQL remains the source of truth for datasets, media metadata,
annotations, classes, verification and split state. MinIO stores file objects;
it is not the annotation database.

## Buckets

| Bucket | Current use | Lifecycle |
| --- | --- | --- |
| `visiox-media` | Dataset media, thumbnails, import staging, label cache and per-job label snapshots | Application-managed |
| `visiox-artifacts` | Training artifacts and model registry files | Application-managed |
| `visiox-tmp` | Reserved for future temporary exports/uploads | Configure a lifecycle before use |

Only claim a lifecycle rule after verifying it in the MinIO console or with
`mc ilm rule ls`. The repository does not create a seven-day rule automatically.

## Media object paths

`datasets.models.media_upload_path` keys objects by project owner, not team:

```text
visiox-media/
└── users/{owner_id}_{owner_slug}/
    └── projects/{project_id}_{project_slug}/
        └── datasets/{dataset_id}_{dataset_slug}/
            └── v{version}/
                ├── raw/{filename}
                │   └── thumbs/{stem}.jpg
                └── augmented/{filename}
                    └── thumbs/{stem}.jpg
```

Example:

```text
users/7_admin/projects/30_truck-detection/datasets/30_truck-v1/v1/raw/frame_001.jpg
users/7_admin/projects/30_truck-detection/datasets/30_truck-v1/v1/raw/thumbs/frame_001.jpg
```

IDs guarantee uniqueness. Slugs are lowercase, normalized to `-` and truncated
to 40 characters. Team membership grants access but does not change storage
paths.

## Dataset import staging

Uploads are staged in the default storage before the Celery worker imports
them:

```text
visiox-media/import-staging/datasets/{dataset_id}/jobs/{job_id}/{file}
```

The API saves staging descriptors in `dataset_import_jobs.staged_files`. The
worker reads the staged files, creates `Media` records in batches, updates job
progress and deletes staging objects in cleanup. Failed jobs retain an error
message in PostgreSQL.

Supported import formats:

- `images`: one or more image files
- `yolo26`: one ZIP containing `data.yaml` and referenced image/label folders
- `coco`: one archive containing compatible COCO JSON and images

YOLO26 `data.yaml` may be under one top-level archive directory. Archives
without `data.yaml` fail with a persisted, user-visible import error.
Re-imports can set `replace_existing=true`: matching image names keep their
existing MinIO object while their annotations and split metadata are updated.
The archive and all labels are validated before existing annotations are
removed. Only image names not already present are written to MinIO.

## Training labels and artifacts

PostgreSQL owns editable annotations. MinIO label files are derived artifacts:

```text
visiox-media/
├── training-cache/datasets/{dataset_id}/revisions/{revision}/...
└── training-jobs/{job_id}/labels/{split}/...

visiox-artifacts/
└── training-jobs/{job_id}/
    ├── artifacts/best.pt
    ├── artifacts/metrics.json
    └── weights/{filename}
```

The dataset cache is replaceable. Per-job label snapshots are immutable inputs
for that training run. GPU agents must use the manifest/split payload rather
than infer splits from canonical media folder names.

## Django configuration

Use placeholders in documentation and service-account credentials in real
environment files:

```env
USE_MINIO=True
MINIO_ENDPOINT=http://10.29.30.20:9000
MINIO_ACCESS_KEY=<MINIO_SERVICE_ACCOUNT>
MINIO_SECRET_KEY=<MINIO_SERVICE_ACCOUNT_SECRET>
MINIO_BUCKET=visiox-media
```

Inside `worker-datasets` on `.20`, Compose overrides only the endpoint:

```env
MINIO_ENDPOINT=http://minio:9000
```

When `USE_MINIO=True`, Django configures `S3Boto3Storage` with path-style
addressing and non-overwriting object names. `core.storage.get_artifacts_storage`
targets `visiox-artifacts` for model files.

When `USE_MINIO=False`, Django uses local `MEDIA_ROOT`. Local and MinIO object
locations are deployment choices; database records and API contracts remain
the same.

## Security rules

- Never commit `.env` or `.env.worker`.
- Never document or paste real access keys into issues or chat.
- Use a scoped MinIO service account, not the root account.
- Keep `.dockerignore` entries for `.env` and `.env.*`; `Dockerfile.worker`
  copies the source tree into the image.
- Presigned URLs may be returned to authorized clients, but raw MinIO
  credentials must never reach the browser or GPU job payload.
- Rotate any credentials that have been exposed in logs, screenshots or chat.

Verify an image does not contain environment files:

```bash
docker run --rm --entrypoint sh <worker-image> -c \
  'find /app -maxdepth 2 -name ".env*" -print'
```

Expected output is empty.

## Health and operations

From `.20`, use the existing Compose project:

```bash
docker compose -p infiniq -f docker-compose.infra.yml ps
curl -fsS http://127.0.0.1:9000/minio/health/live
```

Do not run `docker compose down -v` on the infrastructure project. The `-v`
flag can delete PostgreSQL volumes. MinIO data is bind-mounted at `/data/minio`;
confirm this path and its backups before storage maintenance.

## Dataset import performance

The dataset worker uses one Celery process and bounded storage concurrency:

```env
DATASET_IMPORT_STORAGE_WORKERS=6
DATASET_IMPORT_BATCH_SIZE=24
```

Increase storage workers only after measuring MinIO disk, CPU and network load.
Keep Celery concurrency at `1` so a single archive cannot compete with several
large imports on the same MinIO host.

## Related documentation

- [Dataset worker deployment](DEPLOY_DATASET_WORKER_MINIO.md)
- [Training platform](TRAIN.md)
- [Architecture diagrams](ARCHITECTURE_DIAGRAMS.md)
