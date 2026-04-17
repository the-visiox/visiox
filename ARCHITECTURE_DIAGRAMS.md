# CVAT Source Diagrams

These diagrams were derived from the current repository structure and runtime configuration, mainly from:

- `docker-compose.yml`
- `components/serverless/docker-compose.serverless.yml`
- `site/content/en/docs/contributing/repo-structure.md`
- `cvat/settings/base.py`
- `cvat/urls.py`
- `cvat/apps/engine/urls.py`
- `cvat/apps/lambda_manager/urls.py`
- `cvat/apps/events/views.py`
- `cvat-ui/package.json`
- `cvat-core/package.json`
- `cvat-canvas/package.json`
- `cvat-canvas3d/package.json`
- `cvat-data/package.json`

You can render these blocks directly in GitHub Markdown or in Mermaid Live.

## 1. Architecture Diagram

```mermaid
flowchart LR
    User[Annotator / Admin / Reviewer]
    SDK[Python SDK]
    CLI[CLI]

    subgraph Edge[Edge / Routing]
        Traefik[Traefik reverse proxy]
    end

    subgraph Client[Client Side]
        UI[cvat-ui React SPA]
        Core[cvat-core API/domain layer]
        Canvas2D[cvat-canvas]
        Canvas3D[cvat-canvas3d]
        Data["cvat-data<br/>media decoding"]
    end

    subgraph Backend[CVAT Backend]
        Server[Django API server]
        ImportW["RQ worker<br/>import"]
        ExportW["RQ worker<br/>export"]
        AnnotW["RQ worker<br/>annotation"]
        QualityW["RQ worker<br/>quality reports"]
        WebhookW["RQ worker<br/>webhooks"]
        UtilityW["RQ worker<br/>utils / cleaning / notifications"]
        ConsensusW["RQ worker<br/>consensus"]
        ChunkW["RQ worker<br/>chunks"]
    end

    subgraph DataStores[State and Storage]
        PG[(PostgreSQL)]
        Redis[(Redis in-memory queues)]
        Kvrocks[(Kvrocks / on-disk cache)]
        Media[(CVAT data / logs / keys volumes)]
        Share[Mounted server share]
        Cloud["Cloud storage<br/>S3 / Azure / GCS"]
    end

    subgraph PolicyAI[Policy / AI]
        OPA[Open Policy Agent]
        Nuclio["Nuclio<br/>serverless functions"]
    end

    subgraph Analytics[Analytics]
        Vector[Vector log collector]
        ClickHouse[(ClickHouse events DB)]
        Grafana[Grafana dashboards]
    end

    User --> Traefik
    SDK --> Traefik
    CLI --> Traefik

    Traefik --> UI
    Traefik --> Server

    UI --> Core
    UI --> Canvas2D
    UI --> Canvas3D
    Core --> Data
    Core --> Server

    Server --> PG
    Server --> Redis
    Server --> Kvrocks
    Server --> Media
    Server --> OPA
    Server --> ClickHouse
    Server --> Nuclio
    Server --> Share
    Server --> Cloud
    Server --> Vector

    ImportW --> Redis
    ExportW --> Redis
    AnnotW --> Redis
    QualityW --> Redis
    WebhookW --> Redis
    UtilityW --> Redis
    ConsensusW --> Redis
    ChunkW --> Redis

    ImportW --> PG
    ExportW --> PG
    AnnotW --> PG
    QualityW --> PG
    WebhookW --> PG
    UtilityW --> PG
    ConsensusW --> PG
    ChunkW --> PG

    ImportW --> Media
    ExportW --> Media
    AnnotW --> Media
    ChunkW --> Media

    ImportW --> Cloud
    ExportW --> Cloud
    AnnotW --> Nuclio

    Vector --> ClickHouse
    Grafana --> ClickHouse
    User --> Grafana
```

## 2. Data Flow Diagram

```mermaid
flowchart TD
    User[User]
    SDKCLI[SDK / CLI]
    Cloud[Cloud Storage or Server Share]
    Model[Serverless Model]
    Hook[Webhook Receiver]

    P1[Process: UI / API request handling]
    P2[Process: Task import and media preparation]
    P3[Process: Annotation and frame/chunk delivery]
    P4[Process: Export / backup / dataset conversion]
    P5[Process: Auto-annotation / quality / analytics jobs]
    P6[Process: Event and webhook dispatch]

    D1[(PostgreSQL metadata)]
    D2[(Redis RQ queues)]
    D3[(Media files, chunks, manifests, cache)]
    D4[(ClickHouse event store)]

    User -->|browser actions, uploads, task ops| P1
    SDKCLI -->|REST calls| P1

    P1 -->|task/job/project metadata| D1
    P1 -->|enqueue import/export/annotation/report jobs| D2
    P1 -->|read/write media requests| P3
    P1 -->|log events| P6

    Cloud -->|raw media, annotations, backups| P2
    P2 -->|prepared task data, manifests, chunks| D3
    P2 -->|task/data records| D1
    D2 -->|import jobs| P2

    D3 -->|frames, previews, chunks| P3
    D1 -->|task/job labels and annotations| P3
    P3 -->|annotation updates| D1
    P3 -->|client/server events| P6
    P3 -->|invoke model request| P5
    P3 -->|annotated data back to user| User

    D2 -->|export jobs| P4
    D1 -->|annotations and metadata| P4
    D3 -->|media payloads| P4
    P4 -->|downloadable archive/dataset| User
    P4 -->|exported dataset/backup| Cloud

    D2 -->|annotation, quality, analytics, webhook jobs| P5
    P5 -->|model inference request| Model
    Model -->|predictions / masks / boxes| P5
    P5 -->|quality reports / analytics summaries| D1
    P5 -->|derived events| P6

    P6 -->|event logs| D4
    P6 -->|HTTP callbacks| Hook
```

## 3. Backend Component Diagram

```mermaid
flowchart LR
    subgraph Django[CVAT Django application]
        Engine["engine<br/>Tasks, Jobs, Projects,<br/>Annotations, Media, CloudStorage"]
        IAM["iam<br/>Auth, permissions,<br/>OPA policy enforcement"]
        Orgs[organizations]
        Dataset["dataset_manager<br/>Import/export formats,<br/>dataset conversion"]
        Lambda["lambda_manager<br/>Auto-annotation requests"]
        Events["events<br/>Client/server event logging,<br/>CSV export"]
        Webhooks["webhooks<br/>Domain event subscriptions"]
        Quality["quality_control<br/>Conflicts, reports,<br/>quality settings"]
        Analytics["analytics_report<br/>Derived metrics and reports"]
        Repo[dataset_repo]
        Health[health]
        LogViewer[log_viewer]
    end

    OPA[Open Policy Agent]
    RQ[Redis + django-rq]
    PG[(PostgreSQL)]
    Media[(Media files / cache)]
    ClickHouse[(ClickHouse)]
    Nuclio[Nuclio functions]
    ExternalHooks[External webhook endpoints]

    IAM --> OPA

    Engine --> IAM
    Engine --> Orgs
    Engine --> Dataset
    Engine --> Events
    Engine --> PG
    Engine --> Media
    Engine --> RQ

    Dataset --> Engine
    Dataset --> RQ
    Dataset --> Media

    Lambda --> Engine
    Lambda --> RQ
    Lambda --> Nuclio

    Webhooks --> Engine
    Webhooks --> Events
    Webhooks --> RQ
    Webhooks --> ExternalHooks

    Quality --> Engine
    Quality --> RQ
    Quality --> PG

    Analytics --> Engine
    Analytics --> RQ
    Analytics --> ClickHouse
    Analytics --> PG

    Events --> ClickHouse
    Events --> RQ

    Repo --> Engine
    Health --> Engine
    LogViewer --> ClickHouse
    LogViewer --> IAM
```

## 4. Frontend and Client Component Diagram

```mermaid
flowchart LR
    subgraph Browser[Browser]
        UI["cvat-ui<br/>React + Redux + Ant Design"]
        Pages["Workspaces, tasks,<br/>projects, admin,<br/>analytics screens"]
    end

    subgraph FrontendPackages[Monorepo UI packages]
        Core["cvat-core<br/>REST client, domain models,<br/>uploads via tus-js-client"]
        Canvas2D["cvat-canvas<br/>2D annotation canvas"]
        Canvas3D["cvat-canvas3d<br/>3D workspace canvas"]
        Data["cvat-data<br/>media decoding / zip handling"]
    end

    subgraph ExternalClients[Other repo clients]
        SDK["cvat-sdk<br/>Python client library"]
        CLI["cvat-cli<br/>command-line wrapper"]
    end

    API[CVAT REST API]

    UI --> Pages
    UI --> Core
    UI --> Canvas2D
    UI --> Canvas3D
    Core --> Data
    Core --> API

    SDK --> API
    CLI --> API
    Canvas3D --> Core
```

## Notes

- The main REST surface is centered in `cvat.apps.engine`, then extended by `iam`, `organizations`, `lambda_manager`, `events`, `webhooks`, `quality_control`, and `analytics_report`.
- Queue-backed operations are first-class in this source tree. Import, export, annotation, webhooks, quality reports, analytics reports, cleaning, and notifications all run through `django-rq`.
- Analytics is a separate path from transactional metadata. PostgreSQL stores application state; ClickHouse stores event logs and feeds Grafana dashboards and analytics reports.
- The frontend is intentionally split into reusable packages. `cvat-ui` is the SPA, while `cvat-core`, `cvat-data`, `cvat-canvas`, and `cvat-canvas3d` provide the main client-side layers underneath it.
