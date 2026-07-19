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
| [AUTO_LABEL_ANNOTATION.md](AUTO_LABEL_ANNOTATION.md) | Auto Label specification for bbox and instance segmentation |

Runtime setup starts in the repository [README](../README.md). Environment
templates are `env.example` and `env.worker.example`; never copy real secrets
into documentation.
