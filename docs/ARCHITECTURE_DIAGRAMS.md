# VisioX Architecture Diagrams

This document describes the current native VisioX architecture. PostgreSQL is
the source of truth for metadata and annotations; media and artifacts are stored
locally in development or in MinIO for shared deployments.

## Runtime topology

```mermaid
flowchart LR
    UI[Next.js frontend] -->|JWT REST /api/v1| API[Django API]
    API --> DB[(PostgreSQL)]
    API --> Redis[(Redis)]
    API --> Media[(Local storage or MinIO)]
    Redis --> General[General Celery worker]
    Redis --> Dataset[Dataset Celery worker]
    Redis --> Beat[Celery beat]
    API -->|HTTP job payload| GPU[GPU training / inference agent]
    General --> DB
    Dataset --> DB
    Dataset --> Media
    GPU --> Media
```

Shared deployment ownership:

| Host | Services |
| --- | --- |
| API host (`10.29.30.9`) | Django API, general worker, Celery beat |
| Data host (`10.29.30.20`) | PostgreSQL, Redis, MinIO, dataset worker |
| GPU host | Training and inference agents |

## Backend modules

```mermaid
flowchart TB
    Auth[authentication + core] --> Projects[teams + projects]
    Projects --> Data[datasets]
    Projects --> Labels[annotations]
    Data <--> Labels
    Data --> Training[training]
    Labels --> Training
    Training --> Deploy[deployments]
    Projects --> Billing[billing]
    Projects --> Verse[dataverse]
```

- `datasets/services/media_browser.py` builds native frame/browser payloads.
- `datasets/services/video_extraction.py` selects visually diverse video frames.
- `datasets/services/splitting.py` owns train/validation/test assignment.
- `training/services/` owns artifact and fine-tuning support logic.
- `core/storage.py` selects local or MinIO-compatible storage.

## Dataset import flow

```mermaid
sequenceDiagram
    participant UI as Frontend
    participant API as Django API
    participant Store as Media storage
    participant Queue as Redis
    participant Worker as Dataset worker
    participant DB as PostgreSQL

    UI->>API: POST /datasets/{id}/prepare-import/
    API->>DB: Create pending DatasetImportJob
    API-->>UI: Presigned MinIO PUT URLs
    UI->>Store: Upload large files directly
    UI->>API: POST import-jobs/{job}/commit/
    API->>Queue: Enqueue on datasets
    API-->>UI: 202 + job state
    Queue->>Worker: Run import job
    Worker->>Store: Read staged inputs
    alt Images/archive
        Worker->>DB: Create media and annotations
    else Video extraction
        Worker->>Worker: Compare descriptors and reject frames below the difference threshold
        Worker->>DB: Save diverse frames as image media
    end
    Worker->>Store: Delete staged inputs
    Worker->>DB: Complete job summary
    UI->>API: Poll lightweight dataset/job state
```

Long-running imports must remain on the `datasets` queue. Storage operations
must work with both Django filesystem storage and S3-compatible MinIO storage.

## Native annotation flow

```mermaid
sequenceDiagram
    participant UI as Annotation workspace
    participant API as Django API
    participant DB as PostgreSQL
    participant Store as Media storage

    UI->>API: GET /datasets/{id}/browser/
    API->>DB: Load ordered media, classes, annotations
    API-->>UI: Frames + labels + annotation payload
    UI->>API: GET /datasets/{id}/frames/{frame}/
    API->>Store: Open image object
    API-->>UI: Image bytes
    UI->>API: PUT frame/media annotations
    API->>DB: Replace validated annotation snapshot
    API-->>UI: Saved annotations
```

Frame image endpoints accept the normal Bearer header and the narrowly scoped
query-token authentication required by browser image elements.

## Training flow

```mermaid
sequenceDiagram
    participant UI as Frontend
    participant API as Django API
    participant DB as PostgreSQL
    participant Store as MinIO
    participant Agent as GPU agent

    UI->>API: Create training job
    API->>DB: Validate datasets, classes, architecture
    API->>Store: Build/promote immutable label snapshot
    API->>Agent: Submit job payload
    Agent->>Store: Read media and labels
    Agent->>API: Metrics callbacks
    API->>DB: Persist metrics and status
    Agent->>Store: Write model artifacts
    Agent->>API: Completion callback
    API->>DB: Register model artifacts
```

Class order is captured in the training job schema and must use the explicit
project class index. Canonical media is never rearranged into physical split
folders; PostgreSQL split metadata and immutable label snapshots define the run.

## Storage layout

```text
visiox-media/
  users/{owner}_{slug}/projects/{project}_{slug}/datasets/{dataset}_{slug}/
    v{version}/raw/...
    v{version}/augmented/...
  import-staging/datasets/{dataset_id}/jobs/{job_id}/...
  training-cache/datasets/{dataset_id}/revisions/{revision}/...
  training-jobs/{job_id}/labels/{split}/...

visiox-artifacts/
  training-jobs/{job_id}/weights/...
  training-jobs/{job_id}/plots/...
```

Never expose MinIO credentials to the frontend. API responses provide protected
application endpoints or time-limited storage URLs as appropriate.

## Queue ownership

| Queue | Work |
| --- | --- |
| `celery` | General background work, augmentation, cache cleanup |
| `datasets` | Dataset imports and video frame extraction |
| `gpu_training` | GPU-host training execution where configured |

Dataset and general workers use `Dockerfile.worker`. The data-host Compose stack
uses project name `infiniq`; operational commands must include `-p infiniq`.
