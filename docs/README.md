# VisioX Backend Documentation

| Document | Scope |
| --- | --- |
| [API.md](API.md) | REST API under `/api/v1/` |
| [ARCHITECTURE_DIAGRAMS.md](ARCHITECTURE_DIAGRAMS.md) | Logical and physical architecture |
| [DATABASE.md](DATABASE.md) | PostgreSQL tables and relationships |
| [STORAGE.md](STORAGE.md) | MinIO buckets, paths and security |
| [DEPLOY_DATASET_WORKER_MINIO.md](DEPLOY_DATASET_WORKER_MINIO.md) | `.20` dataset-worker deployment and operations |
| [AUGMENTATION_AND_SCALING.md](AUGMENTATION_AND_SCALING.md) | Dataset background jobs and scaling |
| [TRAIN.md](TRAIN.md) | Training orchestration and GPU agent contract |
| [ROADMAP.md](ROADMAP.md) | Product and infrastructure roadmap |

## Current operational baseline

- API, beat and `general-worker` run on `10.29.30.9`.
- PostgreSQL, Redis, MinIO and `dataset-worker` run on `10.29.30.20`.
- `.20` uses Compose project `infiniq`.
- General, dataset and GPU workers listen to `celery`, `datasets` and
  `gpu_training` respectively.
- Django workers use `Dockerfile.worker` and run as `uid=10001(visiox)`.
- Celery node suffixes are dynamic container IDs.

Do not copy real values from `.env` into documentation. All documented secrets
must remain placeholders.

Environment templates are stored at `env.example` for `.9` and
`env.worker.example` for the dataset worker on `.20`.
