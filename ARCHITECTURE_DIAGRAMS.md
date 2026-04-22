# VisioX Backend Source Diagrams

These diagrams were derived from the current VisioX Django repository structure and runtime configuration, mainly from:

- `docker-compose.yml`
- `requirements.txt`
- `visiox/settings.py`
- `visiox/urls.py`
- `visiox/celery.py`
- `authentication/urls.py`
- `teams/urls.py`
- `projects/urls.py`
- `datasets/urls.py`
- `datasets/services/cvat.py`
- `annotations/urls.py`
- `training/urls.py`
- `deployments/urls.py`
- `billing/urls.py`

They intentionally mirror the style of `cvat/ARCHITECTURE_DIAGRAMS.md`, but describe VisioX as the orchestration layer around its own Django API, local or S3 media storage, Celery workers, Stripe billing, and optional CVAT-backed annotation.

You can render these blocks directly in GitHub Markdown or in Mermaid Live.

## 1. Architecture Diagram

```mermaid
flowchart LR
    User[Workspace user / Admin]
    Frontend[visiox-ui Next.js app]
    APIClient[External API client]

    subgraph Backend[VisioX Django Backend]
        API[Django REST API]
        Auth[JWT auth and API key auth]
        CeleryW["Celery worker<br/>training, deployment, sync jobs"]
        CeleryB["Celery beat<br/>scheduled jobs"]
        Docs["OpenAPI docs<br/>drf-spectacular"]
        Silk[Django Silk profiler]
    end

    subgraph Apps[Domain Apps]
        Teams[teams]
        Projects[projects]
        Datasets[datasets]
        Annotations[annotations]
        Training[training]
        Deployments[deployments]
        Billing[billing]
        Core[core user model and permissions]
    end

    subgraph DataStores[State and Storage]
        PG[(PostgreSQL)]
        Redis[(Redis broker and result backend)]
        Media[(Local media volume)]
        S3[(Optional S3 bucket)]
    end

    subgraph External[External Services]
        CVAT["CVAT server<br/>tasks, jobs, frames, labels"]
        Stripe[Stripe API and webhooks]
        Inference["Inference runtime / endpoint target"]
    end

    User --> Frontend
    Frontend --> API
    APIClient --> API

    API --> Auth
    API --> Docs
    API --> Silk
    API --> Core
    API --> Teams
    API --> Projects
    API --> Datasets
    API --> Annotations
    API --> Training
    API --> Deployments
    API --> Billing

    Datasets --> CVAT
    Annotations --> CVAT
    Billing --> Stripe
    Deployments --> Inference

    API --> PG
    API --> Media
    API --> S3
    API --> Redis
    API --> CeleryW
    CeleryB --> Redis
    CeleryW --> Redis
    CeleryW --> PG
    CeleryW --> Media
    CeleryW --> S3
    CeleryW --> CVAT
    CeleryW --> Inference
```

## 2. Data Flow Diagram

```mermaid
flowchart TD
    User[User]
    UI[visiox-ui browser app]
    API[Django REST API]
    CVAT[CVAT API and SDK]
    Stripe[Stripe]
    ModelRuntime[Model training / inference runtime]

    P1[Process: authentication and workspace navigation]
    P2[Process: project and dataset management]
    P3[Process: media upload and frame delivery]
    P4[Process: annotation, review, quality, export]
    P5[Process: training jobs and experiment metrics]
    P6[Process: model registry and deployment endpoints]
    P7[Process: billing, usage, API keys, webhooks]

    D1[(PostgreSQL application metadata)]
    D2[(Redis Celery queues and results)]
    D3[(Local media volume or S3 object storage)]

    User --> UI
    UI -->|JWT login, token refresh, profile| P1
    P1 --> API
    P1 --> D1

    UI -->|teams, projects, datasets| P2
    P2 --> API
    P2 --> D1
    P2 -->|ensure project/task, sync state| CVAT

    UI -->|uploads and browser requests| P3
    P3 --> API
    P3 --> D3
    P3 -->|task data upload, frame proxy| CVAT
    P3 -->|media and dataset records| D1
    P3 -->|frame bytes, thumbnails, media metadata| UI

    UI -->|labels, shapes, tracks, reviews| P4
    P4 --> API
    P4 --> D1
    P4 -->|job annotations and task annotations| CVAT
    P4 -->|COCO, YOLO, VOC export| UI

    UI -->|start, stop, inspect jobs| P5
    P5 --> API
    P5 -->|enqueue work| D2
    D2 -->|training tasks| ModelRuntime
    P5 -->|jobs, experiments, metrics| D1

    UI -->|registry and endpoints| P6
    P6 --> API
    P6 --> D1
    P6 -->|start, stop, invoke| ModelRuntime

    UI -->|plans, subscriptions, usage, API keys| P7
    Stripe -->|checkout and webhook events| P7
    P7 --> API
    P7 --> D1
```

## 3. Backend Component Diagram

```mermaid
flowchart LR
    subgraph Django[VisioX Django application]
        Core["core<br/>custom user model,<br/>permissions, JWT query auth"]
        Auth["authentication<br/>login, register, logout,<br/>me, token refresh"]
        Teams["teams<br/>teams, members, roles"]
        Projects["projects<br/>project metadata,<br/>CVAT project mapping"]
        Datasets["datasets<br/>dataset records, media,<br/>CVAT task mapping, browser, frames"]
        Annot["annotations<br/>classes, media annotations,<br/>jobs, reviews, quality, export"]
        Training["training<br/>architectures, training jobs,<br/>experiments, metrics"]
        Deploy["deployments<br/>model registry, endpoints,<br/>monitoring, drift alerts"]
        Billing["billing<br/>plans, subscriptions,<br/>usage, API keys, webhooks"]
    end

    DRF[Django REST Framework]
    JWT[SimpleJWT]
    Celery[Celery]
    Beat[django-celery-beat]
    Spectacular[drf-spectacular]
    Silk[Django Silk]

    PG[(PostgreSQL)]
    Redis[(Redis)]
    Media[(Media files)]
    S3[(Optional S3)]
    CVAT[CVAT SDK / REST]
    Stripe[Stripe]

    DRF --> Core
    DRF --> Auth
    DRF --> Teams
    DRF --> Projects
    DRF --> Datasets
    DRF --> Annot
    DRF --> Training
    DRF --> Deploy
    DRF --> Billing

    Auth --> JWT
    Core --> PG
    Teams --> PG
    Projects --> PG
    Datasets --> PG
    Annot --> PG
    Training --> PG
    Deploy --> PG
    Billing --> PG

    Datasets --> Media
    Datasets --> S3
    Datasets --> CVAT
    Annot --> CVAT
    Billing --> Stripe

    Training --> Celery
    Deploy --> Celery
    Datasets --> Celery
    Beat --> Celery
    Celery --> Redis
    Celery --> PG

    Spectacular --> DRF
    Silk --> DRF
```

## 4. CVAT Integration Diagram

```mermaid
sequenceDiagram
    participant UI as visiox-ui
    participant API as VisioX Django API
    participant DB as PostgreSQL
    participant Media as Media storage
    participant CVAT as CVAT API

    UI->>API: Create project / dataset
    API->>DB: Save VisioX project and dataset
    API->>CVAT: Create CVAT project if needed
    API->>CVAT: Create CVAT task for dataset
    API->>DB: Store cvat_project_id and cvat_task_id

    UI->>API: Upload image or video
    API->>Media: Store original media
    API->>DB: Save media metadata
    API->>CVAT: Upload task data when CVAT mode is enabled

    UI->>API: Open data browser
    API->>CVAT: Fetch task labels, metadata, annotations
    API->>DB: Map frames to VisioX Media rows when possible
    API-->>UI: Frames, labels, annotation counts

    UI->>API: Request frame image
    API->>CVAT: Fetch frame bytes from task data
    API-->>UI: Proxied image bytes

    CVAT->>API: Project/task/job webhook event
    API->>DB: Update linked dataset state
```

## 5. API Surface Diagram

```mermaid
flowchart TB
    Root[/api/]
    Auth[/api/auth/]
    Teams[/api/teams/]
    Projects[/api/projects/]
    Datasets[/api/datasets/]
    Annotations[/api/annotations/ and /api/classes/]
    Jobs[/api/jobs/ and /api/tasks/]
    Training[/api/architectures/ and /api/training-jobs/]
    Deploy[/api/registry/ and /api/endpoints/]
    Billing[/api/plans/, subscriptions, usage, api-keys, webhooks]
    Docs[/api/schema/, /api/docs/, /api/redoc/]

    Root --> Auth
    Root --> Teams
    Root --> Projects
    Root --> Datasets
    Root --> Annotations
    Root --> Jobs
    Root --> Training
    Root --> Deploy
    Root --> Billing
    Root --> Docs

    Datasets --> Browser[/api/datasets/{id}/browser/]
    Datasets --> Frames[/api/datasets/{id}/frames/{frame}/]
    Datasets --> Export[/api/datasets/{id}/export/]
    Datasets --> Sync[/api/datasets/{id}/sync_cvat/]
    Datasets --> Webhook[/api/datasets/cvat-webhook/]
    Jobs --> JobAnnotations[/api/jobs/{id}/annotations/]
    Jobs --> JobIssues[/api/jobs/{id}/issues/]
```

## Notes

- VisioX is not a CVAT fork. It is a product API that uses CVAT as an optional annotation engine while keeping VisioX projects, datasets, users, billing, training, and deployments in its own Django domain model.
- PostgreSQL stores transactional state. Redis is used by Celery as the broker and result backend. Media is local by default and can move to S3 through `USE_S3`.
- CVAT integration is concentrated in `datasets/services/cvat.py`, with project/task provisioning, task data upload, frame proxying, task stats, browser data, and webhook registration.
- The current Docker Compose stack runs Django API, Celery worker, Celery beat, PostgreSQL, and Redis. CVAT is expected to run separately and is reached through `CVAT_HOST` / `CVAT_PUBLIC_URL`.
