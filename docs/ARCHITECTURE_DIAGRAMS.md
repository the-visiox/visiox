# VisioX Backend — Architecture Diagrams

Derived from the current `visiox` repository. Render in GitHub Markdown or [Mermaid Live](https://mermaid.live).

Source files:
- `docker-compose.yml`, `requirements.txt`, `visiox/settings.py`, `visiox/urls.py`, `visiox/celery.py`
- `core/`, `authentication/`, `teams/`, `projects/`, `datasets/`, `annotations/`
- `training/`, `deployments/`, `billing/`, `dataverse/`
- `datasets/services/cvat.py`, `datasets/standalone.py`
- `billing/backends.py`, `core/jwt_query_auth.py`

---

## 0. Current Physical Deployment

```mermaid
flowchart LR
    UI["visiox-ui\n:3000"] --> API["10.29.30.9\nDjango API :8000"]
    API --> PG[("10.29.30.20\nPostgreSQL :5432")]
    API --> Redis[("10.29.30.20\nRedis :6379")]
    API --> MinIO[("10.29.30.20\nMinIO :9000")]

    Redis --> General[".9 general-worker\nqueue: celery\nconcurrency: 2"]
    Redis --> Dataset[".20 dataset-worker\nqueue: datasets\nconcurrency: 1"]
    Redis --> GPU["GPU worker\nqueue: gpu_training"]

    General --> PG
    General --> MinIO
    Dataset --> PG
    Dataset --> MinIO

    classDef hardened fill:#e8f5e9,stroke:#2e7d32;
    class General,Dataset hardened;
```

The Django workers use `Dockerfile.worker` and run as `uid=10001(visiox)`.
The `.20` infrastructure stack uses Compose project `infiniq`. Worker node
suffixes are dynamic container IDs, not stable hostnames.

---

## 1. System Architecture

```mermaid
flowchart LR
    User["Workspace user / Admin"]
    Frontend["visiox-ui\nNext.js App"]
    APIClient["External API client\n(X-API-KEY or JWT)"]

    subgraph Backend["VisioX Django Backend"]
        API["Django REST API\n(DRF + drf-spectacular)"]
        Auth["Auth layer\nJWT + API Key"]
        CeleryW["Celery workers\nqueue-specific async jobs"]
        CeleryB["Celery beat\nscheduled tasks"]
        Silk["Django Silk\nprofiler (DEBUG)"]
    end

    subgraph Apps["Domain Apps"]
        Core["core\nuser model · permissions"]
        Teams["teams\nteams · members · invitations"]
        Projects["projects\nproject metadata"]
        Datasets["datasets\nmedia · frames · CVAT proxy"]
        Annot["annotations\nclasses · jobs · reviews · export"]
        Training["training\narchitectures · jobs · metrics"]
        Deploy["deployments\nregistry · endpoints · monitoring"]
        Billing["billing\nplans · subscriptions · API keys"]
        Dataverse["dataverse\npublic dataset hub"]
    end

    subgraph DataStores["Persistence"]
        PG[("PostgreSQL\napplication state")]
        Redis[("Redis\nCelery broker + results")]
        Media[("MinIO (visiox-media)\nor local disk")]
    end

    subgraph External["External Services"]
        CVAT["CVAT server\n(optional)"]
        Stripe["Stripe\nbilling webhooks"]
        InfRuntime["Inference runtime\n(endpoint target)"]
    end

    User --> Frontend
    Frontend -->|"Bearer JWT"| API
    APIClient -->|"X-API-KEY"| API

    API --> Auth
    API --> Core
    API --> Teams
    API --> Projects
    API --> Datasets
    API --> Annot
    API --> Training
    API --> Deploy
    API --> Billing
    API --> Dataverse
    API --> Silk

    API --> PG
    API --> Media
    API --> Redis

    Datasets -->|"cvat-sdk + REST"| CVAT
    Annot --> CVAT
    Billing --> Stripe
    Deploy --> InfRuntime

    API --> CeleryW
    CeleryB --> Redis
    CeleryW --> Redis
    CeleryW --> PG
    CeleryW --> Media
    CeleryW --> CVAT
    CeleryW --> InfRuntime
```

---

## 2. Three-Repo Integration

```mermaid
flowchart TB
    subgraph UI["visiox-ui (Next.js)"]
        Frontend["App Router\nReact 19"]
    end

    subgraph Backend["visiox (Django)"]
        DjangoAPI["REST API\nJWT · projects · datasets\ntraining · billing"]
        CVATSvc["datasets/services/cvat.py\ncvat-sdk wrapper"]
        Standalone["datasets/standalone.py\nfallback (VISIOX_STANDALONE)"]
    end

    subgraph CVATRepo["cvat (customized fork)"]
        CVATWeb["CVAT Web App"]
        CVATBackend["CVAT Django backend"]
    end

    Frontend -->|"REST + JWT\n:8000"| DjangoAPI
    DjangoAPI --> CVATSvc
    DjangoAPI --> Standalone
    CVATSvc -->|"cvat-sdk\n:8080"| CVATBackend
    CVATBackend -->|"webhook events\n/api/v1/datasets/cvat-webhook/"| DjangoAPI
    Frontend -->|"iframe SSO\n:8080"| CVATWeb
    CVATBackend --- CVATWeb
```

---

## 3. Authentication Flow

```mermaid
sequenceDiagram
    participant Client
    participant API as Django API
    participant DB as PostgreSQL
    participant OAuth as OAuth Provider

    Note over Client,DB: Email / Password Login
    Client->>API: POST /api/v1/auth/login/ {username, password}
    API->>DB: Validate credentials
    DB-->>API: UserModel
    API-->>Client: {access_token (1h), refresh_token (7d), user}

    Note over Client,DB: Token Refresh
    Client->>API: POST /api/v1/auth/token/refresh/ {refresh}
    API->>DB: Validate + blacklist old refresh token
    API-->>Client: {access (new)}

    Note over Client,OAuth: OAuth Login (Google / GitHub)
    Client->>OAuth: Redirect to provider
    OAuth-->>Client: Authorization code
    Client->>API: POST /api/v1/auth/oauth/ {provider, code, redirect_uri}
    API->>OAuth: Exchange code for user info
    OAuth-->>API: User profile
    API->>DB: Get or create user
    API-->>Client: {access_token, refresh_token, user}

    Note over Client,DB: API Key Auth
    Client->>API: Any request with X-API-KEY header
    API->>DB: SHA256(key) lookup, check is_active + expiry
    DB-->>API: APIKey + linked user
    API-->>Client: Authorized response

    Note over Client,DB: Frame images (AllowAny — no auth required)
    Client->>API: GET /api/v1/datasets/{id}/frames/{n}/
    API-->>Client: Image bytes (no auth required)
```

---

## 4. CVAT Integration & Standalone Mode

```mermaid
sequenceDiagram
    participant UI as visiox-ui
    participant API as Django API
    participant DB as PostgreSQL
    participant Media as Media storage
    participant CVAT as CVAT API

    UI->>API: POST /api/v1/datasets/ {name, project}
    API->>DB: Save Dataset record
    alt CVAT mode (default)
        API->>CVAT: Create CVAT project (if not exists)
        API->>CVAT: Register project webhook
        API->>CVAT: Create CVAT task (async via Celery)
        API->>DB: Store cvat_task_id
    else VISIOX_STANDALONE=true
        API->>DB: Dataset stays native-only
    end

    UI->>API: POST /api/v1/datasets/{id}/upload/ (multipart)
    API->>Media: Store original file
    API->>DB: Save Media row (width, height, original_filename)
    alt CVAT mode + empty task
        API->>CVAT: Upload task data (one-time)
    end

    UI->>API: GET /api/v1/datasets/{id}/browser/
    alt CVAT mode
        API->>CVAT: Fetch labels, frame metadata, annotations
        API-->>UI: Merged browser payload + media IDs
    else VISIOX_STANDALONE
        API->>DB: Build payload from Media + Annotation rows
        API-->>UI: Native browser payload
    end

    UI->>API: GET /api/v1/datasets/{id}/frames/{n}/?token=<jwt>
    alt CVAT mode
        API->>CVAT: Fetch frame bytes
        API-->>UI: Proxied image
    else VISIOX_STANDALONE
        API->>Media: Read stored file
        API-->>UI: Native image bytes
    end

    CVAT->>API: POST /api/v1/datasets/cvat-webhook/ {event, task}
    API->>DB: Update linked Dataset state
```

---

## 5. Annotation Job Lifecycle

```mermaid
stateDiagram-v2
    [*] --> pending : Task created
    pending --> in_progress : POST /tasks/{id}/start/\n(assigned to current user)
    in_progress --> completed : POST /tasks/{id}/complete/
    completed --> review : POST /tasks/{id}/submit_for_review/
    review --> approved : POST /tasks/{id}/approve/
    review --> rejected : POST /tasks/{id}/reject/
    rejected --> in_progress : Re-open for correction
    approved --> [*]

    note right of in_progress
        Annotator draws shapes
        GET/PATCH /api/v1/jobs/{id}/annotations/
        GET/POST /api/v1/jobs/{id}/issues/
    end note

    note right of review
        Reviewer inspects
        POST /api/v1/reviews/ {annotation, status}
        POST /api/v1/reviews/{id}/approve|reject|request_revision/
    end note
```

---

## 6. Data Flow

```mermaid
flowchart TD
    User["User (browser or API client)"]

    subgraph UI["Request Paths"]
        P1["Auth: login · refresh · logout · OAuth"]
        P2["Team & project management"]
        P3["Media upload + frame delivery"]
        P4["Annotation, review, QA, export"]
        P5["Training jobs + experiment metrics"]
        P6["Model registry + deployment endpoints"]
        P7["Billing, usage, API keys, webhooks"]
        P8["DataVerse: share + fork"]
    end

    D1[("PostgreSQL\napp state")]
    D2[("Redis\nCelery queues")]
    D3[("MinIO\nor local disk")]

    API["VisioX Django API"]
    CVAT["CVAT"]
    Stripe["Stripe"]
    MR["Training / inference runtime"]

    User --> P1 --> API --> D1
    P2 --> API --> D1
    P2 -->|"provision CVAT task"| CVAT

    P3 --> API --> D3
    P3 -->|"upload to CVAT task"| CVAT
    API -->|"frame proxy bytes"| User

    P4 --> API --> D1
    P4 -->|"annotations sync"| CVAT
    API -->|"COCO/YOLO/VOC export"| User

    P5 --> API --> D2
    D2 -->|"run_training_job"| MR
    P5 --> D1

    P6 --> API --> D1
    API -->|"start/stop/infer"| MR

    P7 --> API --> D1
    Stripe -->|"subscription events\n/api/v1/webhooks/stripe/"| API
    API -->|"outbound webhook\nX-Visiox-Signature"| User

    P8 --> API --> D1
```

---

## 7. Backend Component Diagram

```mermaid
flowchart LR
    subgraph Django["VisioX Django Application"]
        Core["core\nUserModel · HasPerm · jwt_query_auth"]
        Auth["authentication\nlogin · register · logout\nOAuth · token refresh"]
        Teams["teams\nTeam · TeamMember · Invitation\nemail invitations"]
        Projects["projects\nProject · task_type\ncvat_project_id"]
        Datasets["datasets\nDataset · Media · MediaLabelProfile\nCVAT proxy · standalone fallback"]
        Annot["annotations\nClass · Annotation\nLabelingTask · JobIssue · Review\nbulk ops · export · QA"]
        Training["training\nModelArchitecture · TrainingJob\nExperiment · RunMetric"]
        Deploy["deployments\nModelRegistry · InferenceEndpoint\nMonitoringLog · DriftAlert"]
        Billing["billing\nPlan · Subscription · UsageRecord\nAPIKey · Webhook · Stripe"]
        Dataverse["dataverse\nDataverseProject\nshare · fork"]
    end

    DRF["Django REST Framework"]
    JWT["SimpleJWT"]
    APIKeyAuth["APIKeyAuthentication\n(billing/backends.py)"]
    Celery["Celery 5"]
    Beat["django-celery-beat"]
    Spectacular["drf-spectacular\nOpenAPI 3.0"]
    Silk["django-silk\nprofiler"]

    PG[("PostgreSQL")]
    Redis[("Redis")]
    MediaFS[("Local media files\n(USE_MINIO=False)")]
    MinIO[("MinIO S3-compatible\nvisiox-media · visiox-artifacts · visiox-tmp")]
    CVATSdk["CVAT SDK / REST"]
    StripeAPI["Stripe API"]

    DRF --> Core & Auth & Teams & Projects & Datasets & Annot & Training & Deploy & Billing & Dataverse
    Auth --> JWT
    Billing --> APIKeyAuth

    Core & Teams & Projects & Datasets & Annot & Training & Deploy & Billing & Dataverse --> PG
    Datasets --> MediaFS & MinIO & CVATSdk
    Annot --> CVATSdk
    Billing --> StripeAPI

    Training & Deploy & Billing & Datasets --> Celery
    Beat --> Celery
    Celery --> Redis & PG

    Spectacular --> DRF
    Silk --> DRF
```

---

## 8. Celery Background Tasks

```mermaid
flowchart LR
    subgraph Triggers["Trigger Events"]
        T1["Dataset import queued"]
        T2["Training job status set to queued"]
        T6["Augmentation or label cache requested"]
        T3["Periodic (django-celery-beat)"]
        T4["Manual trigger\nPOST /endpoints/{id}/trigger_drift_check/"]
        T5["Outbound webhook event\n(training.completed, drift.created, etc.)"]
    end

    subgraph Workers["Celery Workers"]
        W1["dataset-worker on .20\nprocess_dataset_import_task\nqueue: datasets"]
        W2["general-worker on .9\nrun_training_job\nqueue: celery"]
        W5["general-worker on .9\naugmentation + label cache\nqueue: celery"]
        W3["check_endpoint_drift(endpoint_id)\n60-min window analysis\n→ DriftAlert if conf < threshold"]
        W4["deliver_webhook(webhook_id, event, payload)\nPOST to URL\nX-Visiox-Signature: HMAC-SHA256"]
    end

    subgraph State["State Updates"]
        DB[("PostgreSQL")]
        MinIO["MinIO"]
    end

    T1 --> W1
    T2 --> W2
    T6 --> W5
    T3 --> W3
    T4 --> W3
    T5 --> W4

    W1 --> DB
    W1 --> MinIO
    W2 --> DB
    W5 --> DB
    W5 --> MinIO
    W3 --> DB
    W4 -->|HTTP POST| ExternalURL["External webhook URL"]
```

---

## 9. API Surface

```mermaid
flowchart TB
    Root["/api/v1/"]

    Root --> AuthR["/api/v1/auth/\nlogin · register · logout · me · oauth · token/refresh"]
    Root --> TeamsR["/api/v1/teams/ · /api/v1/invitations/\nCRUD + members + email invitations"]
    Root --> ProjectsR["/api/v1/projects/\nCRUD"]
    Root --> DatasetsR["/api/v1/datasets/"]
    Root --> AnnR["/api/v1/classes/ · /api/v1/annotations/\n/api/v1/tasks/ · /api/v1/jobs/ · /api/v1/reviews/"]
    Root --> TrainR["/api/v1/architectures/ · /api/v1/training-jobs/ · /api/v1/experiments/"]
    Root --> DeployR["/api/v1/registry/ · /api/v1/endpoints/\n/api/v1/monitoring/ · /api/v1/drift-alerts/"]
    Root --> BillingR["/api/v1/plans/ · /api/v1/subscriptions/ · /api/v1/usage/\n/api/v1/api-keys/ · /api/v1/webhooks/"]
    Root --> DataverseR["/api/v1/dataverse/"]
    Root --> DocsR["/api/schema/ · /api/docs/ · /api/redoc/"]

    DatasetsR --> DS1["/api/v1/datasets/{id}/annotate_url/"]
    DatasetsR --> DS2["/api/v1/datasets/{id}/browser/"]
    DatasetsR --> DS3["/api/v1/datasets/{id}/frames/{n}/\n(JWT header or ?token=)"]
    DatasetsR --> DS4["/api/v1/datasets/{id}/upload/ · /upload_batch/"]
    DatasetsR --> DS5["/api/v1/datasets/{id}/delete_media/"]
    DatasetsR --> DS6["/api/v1/datasets/{id}/stats/ · /sync_cvat/ · /export/"]
    DatasetsR --> DS7["/api/v1/datasets/cvat-webhook/\n(AllowAny)"]

    AnnR --> AN1["/api/v1/media/{id}/annotations/\n(GET · PUT — full snapshot)"]
    AnnR --> AN2["/api/v1/media/{id}/label-profile/"]
    AnnR --> AN3["/api/v1/jobs/{id}/annotations/\n(GET · PATCH)"]
    AnnR --> AN4["/api/v1/jobs/{id}/issues/"]
    AnnR --> AN5["/api/v1/jobs/{id}/start|complete\n|submit_for_review|approve|reject/"]
    AnnR --> AN6["/api/v1/datasets/{id}/quality/\n/api/v1/media/{id}/quality/"]

    BillingR --> B1["/api/v1/webhooks/stripe/\n(AllowAny)"]
    DataverseR --> DV1["/api/v1/dataverse/share-project/\n/api/v1/dataverse/{id}/fork/"]
```

---

## 10. Billing & Stripe Flow

```mermaid
sequenceDiagram
    participant User
    participant API as Django API
    participant DB as PostgreSQL
    participant Stripe as Stripe API
    participant Celery as Celery

    User->>API: POST /api/v1/subscriptions/ {team, plan}
    API->>Stripe: Create customer + subscription
    Stripe-->>API: {stripe_customer_id, stripe_subscription_id}
    API->>DB: Save Subscription (status: active)
    API-->>User: Subscription object

    Note over Stripe,API: Stripe sends events to webhook
    Stripe->>API: POST /api/v1/webhooks/stripe/ (Stripe-Signature header)
    API->>API: Validate HMAC signature (STRIPE_WEBHOOK_SECRET)
    API->>DB: Update Subscription status (past_due / cancelled / etc.)

    Note over User,Celery: Outbound webhook (e.g. training.job.completed)
    API->>DB: Event fires (TrainingJob → completed)
    API->>Celery: deliver_webhook(webhook_id, event, payload)
    Celery->>DB: Fetch Webhook.url + secret
    Celery->>ExternalURL["External URL"]: POST payload\nX-Visiox-Signature: HMAC-SHA256(secret, payload)

    Note over User,DB: API Key creation
    User->>API: POST /api/v1/api-keys/ {name, team, expires_at?}
    API->>DB: Store SHA256(key), prefix
    API-->>User: {key: "vx_sk_...", prefix} ← raw key shown ONCE

    Note over User,DB: API Key usage
    User->>API: Any request with X-API-KEY: <raw key>
    API->>DB: SHA256(header) → lookup APIKey
    API->>DB: Update last_used
    API-->>User: Authorized response
```

---

## 11. DataVerse Fork Flow

```mermaid
sequenceDiagram
    participant User
    participant API as Django API
    participant DB as PostgreSQL
    participant Media as Media storage

    User->>API: POST /api/v1/dataverse/share-project/ {project, title, tags, license}
    API->>DB: Validate user owns project
    API->>DB: Create DataverseProject (is_public=true)
    API-->>User: DataverseProject object

    User->>API: GET /api/v1/dataverse/?search=traffic
    API->>DB: Query public DataverseProjects
    API->>DB: Increment view_count on detail retrieve
    API-->>User: Paginated list

    User->>API: POST /api/v1/dataverse/{id}/fork/ {team, name?}
    API->>DB: Validate user has team membership
    API->>DB: Deep copy Project → new Project
    API->>DB: Copy all Class records
    loop Per Dataset
        API->>DB: Copy Dataset record
        loop Per Media file
            API->>Media: Copy media file
            API->>DB: Copy Media row (new dataset FK)
            API->>DB: Copy Annotation rows
        end
    end
    API->>DB: Increment fork_count on source
    API-->>User: {project_id, name}
```

---

## 12. MinIO Storage Architecture

```mermaid
flowchart LR
    subgraph Django["Django Backend"]
        Upload["Media upload\n(datasets/models.py\nmedia_upload_path)"]
        ArtifactUpload["Artifact upload\n(deployments/models.py\nartifact_upload_path)"]
        Storage["django-storages\nS3Boto3Storage"]
        ArtifactStorage["core/storage.py\nget_artifacts_storage()"]
    end

    subgraph MinIO["MinIO  (10.29.30.20:9000)"]
        M1[("visiox-media\npermanent\ndataset images")]
        M2[("visiox-artifacts\npermanent\ntrained model weights")]
        M3[("visiox-tmp\nreserved\nlifecycle must be configured")]
    end

    Upload -->|"USE_MINIO=True"| Storage --> M1
    ArtifactUpload --> ArtifactStorage --> M2

    subgraph Path["Object path  (visiox-media)"]
        P["users/{owner_id}_{slug}/\n  projects/{id}_{slug}/\n    datasets/{id}_{slug}/\n      v{version}/\n        raw|augmented/\n          {filename}\n          thumbs/{stem}.jpg"]
    end

    subgraph Path2["Object path  (visiox-artifacts)"]
        P2["training-jobs/{job_id}/\n  artifacts/{filename}\n  weights/{filename}"]
    end

    M1 -.->|example| P
    M2 -.->|example| P2
```

**Environment variables (`.env`):**

| Variable | Example | Purpose |
| --- | --- | --- |
| `USE_MINIO` | `True` | Enable MinIO storage backend |
| `MINIO_ENDPOINT` | `http://10.29.30.20:9000` | MinIO server URL |
| `MINIO_ACCESS_KEY` | `<service-account>` | Scoped MinIO service account |
| `MINIO_SECRET_KEY` | `<service-account-secret>` | Secret; never commit or document the real value |
| `MINIO_BUCKET` | `visiox-media` | Default bucket for media uploads |

**Management commands for data migration:**

| Command | Purpose |
| --- | --- |
| `migrate_to_minio` | Local disk → MinIO `visiox-data/teams/` |
| `migrate_to_new_structure` | `visiox-data/teams/{id}/` → `visiox-media/orgs/{id}/v{version}/` |
| `migrate_to_slug_paths` | `orgs/{id}/` → `orgs/{id}_{slug}/` (human-readable rename) |

---

## Agent Constraints

- Do not add boxes, arrows, or endpoints unless they exist in the codebase or are explicitly marked as future work.
- Keep `VISIOX_STANDALONE` vs CVAT-enabled mode distinct — both are valid runtime configurations.
- `visiox-ui`, `visiox`, and `cvat` are three separate repos with separate responsibilities.
- `billing/backends.py` provides API key authentication — it is separate from JWT and should not be collapsed into it.
- When documenting background work, stay conservative: only show Celery tasks that exist in `tasks.py` files.

## Notes

- PostgreSQL stores all transactional state. Redis is the Celery broker and result backend. Media is local by default; set `USE_MINIO=True` in `.env` to route all uploads to MinIO (`MINIO_ENDPOINT`).
- MinIO buckets: `visiox-media` stores media/import staging/derived labels; `visiox-artifacts` stores trained model artifacts; `visiox-tmp` is reserved until a verified lifecycle is configured. Media paths use `users/{owner_id}_{slug}/projects/{id}_{slug}/datasets/{id}_{slug}/v{version}/{category}/{filename}`.
- Compose is split by host: `.9` runs `api`, `worker`, and `beat`; `.20` project `infiniq` runs `db`, `redis`, `minio`, and `worker-datasets`. CVAT runs separately and is reached via `CVAT_INTERNAL_HOST`.
- CVAT integration is concentrated in `datasets/services/cvat.py`. All provisioning, frame proxying, browser payload assembly, one-time data upload, deleted-frame sync, orphan repair, and webhook registration live there.
- `VISIOX_STANDALONE=true` disables all CVAT calls and falls back to `datasets/standalone.py` for browser data and frame delivery.
- The outbound webhook system (`billing/`) fires events like `training.job.completed` and `deployment.drift_alert.created` via Celery, signed with HMAC-SHA256.
