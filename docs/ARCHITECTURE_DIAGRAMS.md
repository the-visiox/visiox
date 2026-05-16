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
- `datasets/views/dataset_view.py`
- `datasets/views/webhook_view.py`
- `datasets/services/cvat.py`
- `datasets/standalone.py`
- `annotations/urls.py`
- `annotations/views/task_view.py`
- `annotations/views/export_view.py`
- `annotations/views/quality_view.py`
- `training/urls.py`
- `deployments/urls.py`
- `billing/urls.py`
- `billing/backends.py`
- `core/jwt_query_auth.py`

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
        Auth[JWT auth plus API key auth]
        CeleryW["Celery worker<br/>async jobs"]
        CeleryB["Celery beat<br/>scheduled jobs"]
        Docs["OpenAPI docs<br/>drf-spectacular"]
        Silk["Django Silk profiler<br/>debug-focused"]
    end

    subgraph Apps[Domain Apps]
        Core[core user model and permissions]
        Teams[teams]
        Projects[projects]
        Datasets[datasets]
        Annotations[annotations]
        Training[training]
        Deployments[deployments]
        Billing[billing]
    end

    subgraph DataStores[State and Storage]
        PG[(PostgreSQL)]
        Redis[(Redis broker and result backend)]
        Media[(Local media volume)]
        S3[(Optional S3 bucket)]
    end

    subgraph External[External Services]
        CVAT["CVAT server<br/>optional task, frame, webhook integration"]
        Stripe[Stripe API and inbound webhook]
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

    API --> PG
    API --> Media
    API --> S3
    API --> Redis

    Datasets --> CVAT
    Annotations --> CVAT
    Billing --> Stripe
    Deployments --> Inference

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
    ModelRuntime[Training / inference runtime]

    P1[Process: authentication and workspace navigation]
    P2[Process: project and dataset management]
    P3[Process: media upload and frame delivery]
    P4[Process: annotation, review, quality, export]
    P5[Process: training jobs and experiment metrics]
    P6[Process: model registry and deployment endpoints]
    P7[Process: billing, usage, API keys, outbound and inbound webhooks]

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
    P2 -->|create and link project/task when CVAT mode is enabled| CVAT

    UI -->|uploads, browser requests, frame requests| P3
    P3 --> API
    P3 --> D3
    P3 -->|task upload, frame proxy, deleted-frame sync when CVAT mode is enabled| CVAT
    P3 -->|media rows and dataset metadata| D1
    P3 -->|frame bytes, thumbnails, media metadata| UI

    UI -->|labels, job annotations, reviews, quality, export| P4
    P4 --> API
    P4 --> D1
    P4 -->|task annotations and labels when CVAT mode is enabled| CVAT
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

    UI -->|plans, subscriptions, usage, API keys, webhook config| P7
    Stripe -->|subscription webhook events| P7
    P7 --> API
    P7 --> D1
```

## 3. Backend Component Diagram

```mermaid
flowchart LR
    subgraph Django[VisioX Django application]
        Core["core<br/>custom user model,<br/>permissions, JWT query auth helper"]
        Auth["authentication<br/>login, register, logout,<br/>me, token refresh"]
        Teams["teams<br/>teams, members, roles"]
        Projects["projects<br/>project metadata,<br/>CVAT project mapping"]
        Datasets["datasets<br/>dataset records, media,<br/>CVAT task mapping, browser, frames,<br/>standalone fallback"]
        Annot["annotations<br/>classes, annotations,<br/>jobs, reviews, quality, export"]
        Training["training<br/>architectures, training jobs,<br/>experiments"]
        Deploy["deployments<br/>model registry, endpoints,<br/>monitoring, drift alerts"]
        Billing["billing<br/>plans, subscriptions,<br/>usage, API keys, webhooks"]
    end

    DRF[Django REST Framework]
    JWT[SimpleJWT]
    APIKey[API key auth backend]
    Celery[Celery]
    Beat[django-celery-beat]
    Spectacular[drf-spectacular]
    Silk[django-silk]

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
    Billing --> APIKey

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
    Billing --> Celery
    Datasets --> Celery
    Beat --> Celery
    Celery --> Redis
    Celery --> PG

    Spectacular --> DRF
    Silk --> DRF
```

## 4. CVAT and Standalone Integration Diagram

```mermaid
sequenceDiagram
    participant UI as visiox-ui
    participant API as VisioX Django API
    participant DB as PostgreSQL
    participant Media as Media storage
    participant CVAT as CVAT API

    UI->>API: Create project / dataset
    API->>DB: Save VisioX project and dataset
    alt CVAT mode
        API->>CVAT: Create CVAT project if needed
        API->>CVAT: Register project webhook
        API->>CVAT: Create CVAT task for dataset
        API->>DB: Store cvat_project_id and cvat_task_id
    else VISIOX_STANDALONE
        API->>DB: Keep dataset native-only
    end

    UI->>API: Upload image or video
    API->>Media: Store original media
    API->>DB: Save media metadata
    alt CVAT mode and task still has no frames
        API->>CVAT: Upload task data once
    else standalone or non-empty CVAT task
        API->>DB: Keep media in VisioX only
    end

    UI->>API: Open data browser
    alt CVAT mode
        API->>CVAT: Fetch labels, frame metadata, annotations
        API-->>UI: Browser payload plus mapped media ids
    else VISIOX_STANDALONE
        API->>DB: Build browser payload from Media and Annotation rows
        API-->>UI: Native browser payload
    end

    UI->>API: Request frame image
    alt CVAT mode
        API->>CVAT: Fetch frame bytes
        API-->>UI: Proxied image bytes
    else VISIOX_STANDALONE
        API->>Media: Read stored image file
        API-->>UI: Native image bytes
    end

    CVAT->>API: Project webhook event
    API->>DB: Update linked dataset state when task mapping exists
```

## 5. API Surface Diagram

```mermaid
flowchart TB
    Root[/api/]
    Auth[/api/auth/]
    Teams[/api/teams/]
    Projects[/api/projects/]
    Datasets[/api/datasets/]
    Classes[/api/classes/]
    Annotations[/api/annotations/]
    Tasks[/api/tasks/ and /api/jobs/]
    Reviews[/api/reviews/]
    Training[/api/architectures/, /api/training-jobs/, /api/experiments/]
    Deploy[/api/registry/, /api/endpoints/, /api/monitoring/, /api/drift-alerts/]
    Billing[/api/plans/, /api/subscriptions/, /api/usage/, /api/api-keys/, /api/webhooks/]
    Docs[/api/schema/, /api/docs/, /api/redoc/]

    Root --> Auth
    Root --> Teams
    Root --> Projects
    Root --> Datasets
    Root --> Classes
    Root --> Annotations
    Root --> Tasks
    Root --> Reviews
    Root --> Training
    Root --> Deploy
    Root --> Billing
    Root --> Docs

    Datasets --> AnnotateURL[/api/datasets/{id}/annotate_url/]
    Datasets --> Stats[/api/datasets/{id}/stats/]
    Datasets --> Media[/api/datasets/{id}/media/]
    Datasets --> Upload[/api/datasets/{id}/upload/]
    Datasets --> UploadBatch[/api/datasets/{id}/upload-batch/]
    Datasets --> DeleteMedia[/api/datasets/{id}/delete-media/]
    Datasets --> Browser[/api/datasets/{id}/browser/]
    Datasets --> Frames[/api/datasets/{id}/frames/{frame}/]
    Datasets --> FrameAnnotations[/api/datasets/{id}/frames/{frame}/annotations/]
    Datasets --> Export[/api/datasets/{id}/export/]
    Datasets --> Quality[/api/datasets/{id}/quality/]
    Datasets --> Sync[/api/datasets/{id}/sync_cvat/]
    Datasets --> Repair[/api/datasets/repair-cvat/]
    Datasets --> CVATWebhook[/api/datasets/cvat-webhook/]

    Tasks --> TaskAnnotations[/api/tasks/{id}/annotations/]
    Tasks --> TaskIssues[/api/tasks/{id}/issues/]
    Tasks --> TaskLifecycle[/api/tasks/{id}/start|complete|submit_for_review|approve|reject/]

    Reviews --> ReviewActions[/api/reviews/{id}/approve|reject|request_revision/]
    Billing --> StripeWebhook[/api/webhooks/stripe/]
```

## Agent Constraints

- Treat this file as a source-guided summary, not a product roadmap. Do not add boxes, arrows, services, or endpoints unless they exist in the codebase or are explicitly marked as future work elsewhere.
- Keep the distinction between `VISIOX_STANDALONE` and CVAT-enabled mode explicit. The backend supports both, and diagrams should not imply that CVAT is always required.
- Keep `visiox-ui`, `visiox`, and `cvat` separated by responsibility. VisioX is not a CVAT fork and should not be documented as if annotation, auth, or billing live inside CVAT.
- Reflect route ownership accurately. Dataset browser, frame proxy, repair, and CVAT webhook behavior live under `datasets`, while job/task annotation lifecycle lives under `annotations`.
- Do not collapse authentication into JWT only. The REST framework also includes API key authentication, and some image endpoints accept JWT via query token patterns.
- When documenting background work, keep Celery usage conservative. Show it where code clearly uses async tasks or scheduled jobs; do not infer unimplemented pipelines.
- Prefer stable nouns from code over marketing language. Examples: `training-jobs`, `experiments`, `registry`, `drift-alerts`, `api-keys`, `webhooks`.
- If a diagram becomes ambiguous, favor notes over invented detail. A short note about optional behavior is better than a confident but inaccurate arrow.

## Notes

- VisioX is not a CVAT fork. It is a Django product API that can use CVAT as an optional annotation engine while keeping projects, datasets, users, billing, training, and deployments in its own domain model.
- PostgreSQL stores transactional state. Redis is used by Celery as the broker and result backend. Media is local by default and can move to S3 through `USE_S3=true`.
- The current Docker Compose stack runs `db`, `redis`, `api`, `worker`, and `beat`. CVAT is expected to run separately and is reached through `CVAT_HOST` and `CVAT_PUBLIC_URL`.
- CVAT integration is concentrated in `datasets/services/cvat.py`, with project/task provisioning, one-time task data upload, browser payload assembly, frame proxying, deleted-frame sync, orphan repair, and webhook registration.
- The API root wires app routers under `/api/`, while auth is mounted at `/api/auth/` and docs are exposed at `/api/schema/`, `/api/docs/`, and `/api/redoc/`.
