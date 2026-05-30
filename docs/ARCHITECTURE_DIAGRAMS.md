# VisioX Backend — Architecture Diagrams

Derived from the current `visiox` repository. Render in GitHub Markdown or [Mermaid Live](https://mermaid.live).

Source files:
- `docker-compose.yml`, `requirements.txt`, `visiox/settings.py`, `visiox/urls.py`, `visiox/celery.py`
- `core/`, `authentication/`, `teams/`, `projects/`, `datasets/`, `annotations/`
- `training/`, `deployments/`, `billing/`, `dataverse/`
- `datasets/services/cvat.py`, `datasets/standalone.py`
- `billing/backends.py`, `core/jwt_query_auth.py`

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
        CeleryW["Celery worker\nasync jobs"]
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
        Media[("Local media\nor S3")]
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
    CVATBackend -->|"webhook events\n/api/datasets/cvat-webhook/"| DjangoAPI
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
    Client->>API: POST /api/auth/login/ {username, password}
    API->>DB: Validate credentials
    DB-->>API: UserModel
    API-->>Client: {access_token (1h), refresh_token (7d), user}

    Note over Client,DB: Token Refresh
    Client->>API: POST /api/auth/token/refresh/ {refresh}
    API->>DB: Validate + blacklist old refresh token
    API-->>Client: {access (new)}

    Note over Client,OAuth: OAuth Login (Google / GitHub)
    Client->>OAuth: Redirect to provider
    OAuth-->>Client: Authorization code
    Client->>API: POST /api/auth/oauth/ {provider, code, redirect_uri}
    API->>OAuth: Exchange code for user info
    OAuth-->>API: User profile
    API->>DB: Get or create user
    API-->>Client: {access_token, refresh_token, user}

    Note over Client,DB: API Key Auth
    Client->>API: Any request with X-API-KEY header
    API->>DB: SHA256(key) lookup, check is_active + expiry
    DB-->>API: APIKey + linked user
    API-->>Client: Authorized response

    Note over Client,DB: Frame images (AllowAny — không cần auth)
    Client->>API: GET /api/datasets/{id}/frames/{n}/
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

    UI->>API: POST /api/datasets/ {name, project}
    API->>DB: Save Dataset record
    alt CVAT mode (default)
        API->>CVAT: Create CVAT project (if not exists)
        API->>CVAT: Register project webhook
        API->>CVAT: Create CVAT task (async via Celery)
        API->>DB: Store cvat_task_id
    else VISIOX_STANDALONE=true
        API->>DB: Dataset stays native-only
    end

    UI->>API: POST /api/datasets/{id}/upload/ (multipart)
    API->>Media: Store original file
    API->>DB: Save Media row (width, height, original_filename)
    alt CVAT mode + empty task
        API->>CVAT: Upload task data (one-time)
    end

    UI->>API: GET /api/datasets/{id}/browser/
    alt CVAT mode
        API->>CVAT: Fetch labels, frame metadata, annotations
        API-->>UI: Merged browser payload + media IDs
    else VISIOX_STANDALONE
        API->>DB: Build payload from Media + Annotation rows
        API-->>UI: Native browser payload
    end

    UI->>API: GET /api/datasets/{id}/frames/{n}/?token=<jwt>
    alt CVAT mode
        API->>CVAT: Fetch frame bytes
        API-->>UI: Proxied image
    else VISIOX_STANDALONE
        API->>Media: Read stored file
        API-->>UI: Native image bytes
    end

    CVAT->>API: POST /api/datasets/cvat-webhook/ {event, task}
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
        GET/PATCH /api/jobs/{id}/annotations/
        GET/POST /api/jobs/{id}/issues/
    end note

    note right of review
        Reviewer inspects
        POST /api/reviews/ {annotation, status}
        POST /api/reviews/{id}/approve|reject|request_revision/
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
    D3[("Media\nlocal or S3")]

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
    Stripe -->|"subscription events\n/api/webhooks/stripe/"| API
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
    MediaFS[("Media files")]
    S3[("Optional S3")]
    CVATSdk["CVAT SDK / REST"]
    StripeAPI["Stripe API"]

    DRF --> Core & Auth & Teams & Projects & Datasets & Annot & Training & Deploy & Billing & Dataverse
    Auth --> JWT
    Billing --> APIKeyAuth

    Core & Teams & Projects & Datasets & Annot & Training & Deploy & Billing & Dataverse --> PG
    Datasets --> MediaFS & S3 & CVATSdk
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
        T1["Dataset created"]
        T2["Training job started\nPOST /training-jobs/{id}/start/"]
        T3["Periodic (django-celery-beat)"]
        T4["Manual trigger\nPOST /endpoints/{id}/trigger_drift_check/"]
        T5["Outbound webhook event\n(training.completed, drift.created, etc.)"]
    end

    subgraph Workers["Celery Workers"]
        W1["provision_cvat_task(dataset_id)\nmax_retries=3, retry_delay=10s"]
        W2["run_training_job(job_id)\nepoch loop → RunMetric rows\nTrainingJob status: queued→running→completed|failed"]
        W3["check_endpoint_drift(endpoint_id)\n60-min window analysis\n→ DriftAlert if conf < threshold"]
        W4["deliver_webhook(webhook_id, event, payload)\nPOST to URL\nX-Visiox-Signature: HMAC-SHA256"]
    end

    subgraph State["State Updates"]
        DB[("PostgreSQL")]
        CVAT["CVAT API"]
    end

    T1 --> W1
    T2 --> W2
    T3 --> W3
    T4 --> W3
    T5 --> W4

    W1 --> CVAT
    W1 --> DB
    W2 --> DB
    W3 --> DB
    W4 -->|HTTP POST| ExternalURL["External webhook URL"]
```

---

## 9. API Surface

```mermaid
flowchart TB
    Root["/api/"]

    Root --> AuthR["/api/auth/\nlogin · register · logout · me · oauth · token/refresh"]
    Root --> TeamsR["/api/teams/ · /api/invitations/\nCRUD + members + email invitations"]
    Root --> ProjectsR["/api/projects/\nCRUD"]
    Root --> DatasetsR["/api/datasets/"]
    Root --> AnnR["/api/classes/ · /api/annotations/\n/api/tasks/ · /api/jobs/ · /api/reviews/"]
    Root --> TrainR["/api/architectures/ · /api/training-jobs/ · /api/experiments/"]
    Root --> DeployR["/api/registry/ · /api/endpoints/\n/api/monitoring/ · /api/drift-alerts/"]
    Root --> BillingR["/api/plans/ · /api/subscriptions/ · /api/usage/\n/api/api-keys/ · /api/webhooks/"]
    Root --> DataverseR["/api/dataverse/"]
    Root --> DocsR["/api/schema/ · /api/docs/ · /api/redoc/"]

    DatasetsR --> DS1["/api/datasets/{id}/annotate_url/"]
    DatasetsR --> DS2["/api/datasets/{id}/browser/"]
    DatasetsR --> DS3["/api/datasets/{id}/frames/{n}/\n(AllowAny, ?token= support)"]
    DatasetsR --> DS4["/api/datasets/{id}/upload/ · /upload_batch/"]
    DatasetsR --> DS5["/api/datasets/{id}/delete_media/"]
    DatasetsR --> DS6["/api/datasets/{id}/stats/ · /sync_cvat/ · /export/"]
    DatasetsR --> DS7["/api/datasets/cvat-webhook/\n(AllowAny)"]

    AnnR --> AN1["/api/media/{id}/annotations/\n(GET · PUT — full snapshot)"]
    AnnR --> AN2["/api/media/{id}/label-profile/"]
    AnnR --> AN3["/api/jobs/{id}/annotations/\n(GET · PATCH)"]
    AnnR --> AN4["/api/jobs/{id}/issues/"]
    AnnR --> AN5["/api/jobs/{id}/start|complete\n|submit_for_review|approve|reject/"]
    AnnR --> AN6["/api/datasets/{id}/quality/\n/api/media/{id}/quality/"]

    BillingR --> B1["/api/webhooks/stripe/\n(AllowAny)"]
    DataverseR --> DV1["/api/dataverse/share-project/\n/api/dataverse/{id}/fork/"]
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

    User->>API: POST /api/subscriptions/ {team, plan}
    API->>Stripe: Create customer + subscription
    Stripe-->>API: {stripe_customer_id, stripe_subscription_id}
    API->>DB: Save Subscription (status: active)
    API-->>User: Subscription object

    Note over Stripe,API: Stripe sends events to webhook
    Stripe->>API: POST /api/webhooks/stripe/ (Stripe-Signature header)
    API->>API: Validate HMAC signature (STRIPE_WEBHOOK_SECRET)
    API->>DB: Update Subscription status (past_due / cancelled / etc.)

    Note over User,Celery: Outbound webhook (e.g. training.job.completed)
    API->>DB: Event fires (TrainingJob → completed)
    API->>Celery: deliver_webhook(webhook_id, event, payload)
    Celery->>DB: Fetch Webhook.url + secret
    Celery->>ExternalURL["External URL"]: POST payload\nX-Visiox-Signature: HMAC-SHA256(secret, payload)

    Note over User,DB: API Key creation
    User->>API: POST /api/api-keys/ {name, team, expires_at?}
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

    User->>API: POST /api/dataverse/share-project/ {project, title, tags, license}
    API->>DB: Validate user owns project
    API->>DB: Create DataverseProject (is_public=true)
    API-->>User: DataverseProject object

    User->>API: GET /api/dataverse/?search=traffic
    API->>DB: Query public DataverseProjects
    API->>DB: Increment view_count on detail retrieve
    API-->>User: Paginated list

    User->>API: POST /api/dataverse/{id}/fork/ {team, name?}
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

## Agent Constraints

- Do not add boxes, arrows, or endpoints unless they exist in the codebase or are explicitly marked as future work.
- Keep `VISIOX_STANDALONE` vs CVAT-enabled mode distinct — both are valid runtime configurations.
- `visiox-ui`, `visiox`, and `cvat` are three separate repos with separate responsibilities.
- `billing/backends.py` provides API key authentication — it is separate from JWT and should not be collapsed into it.
- When documenting background work, stay conservative: only show Celery tasks that exist in `tasks.py` files.

## Notes

- PostgreSQL stores all transactional state. Redis is the Celery broker and result backend. Media is local by default and can be moved to S3 via `USE_S3=true`.
- The Docker Compose stack runs `db`, `redis`, `api`, `worker`, and `beat`. CVAT runs separately and is reached via `CVAT_INTERNAL_HOST`.
- CVAT integration is concentrated in `datasets/services/cvat.py`. All provisioning, frame proxying, browser payload assembly, one-time data upload, deleted-frame sync, orphan repair, and webhook registration live there.
- `VISIOX_STANDALONE=true` disables all CVAT calls and falls back to `datasets/standalone.py` for browser data and frame delivery.
- The outbound webhook system (`billing/`) fires events like `training.job.completed` and `deployment.drift_alert.created` via Celery, signed with HMAC-SHA256.
