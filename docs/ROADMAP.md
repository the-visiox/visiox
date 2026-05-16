# VisioX — Product Roadmap

> **Engineering setup:** For running the Visiox API, database, and pairing with **visiox-ui**, see the repo root **`README.md`** (Docker vs `localhost`, ports `5432` / `5433`, JWT, CORS).

> Reference: [Datature.io](https://datature.io) — All-in-One Vision AI Platform

---

## Overview

| Attribute | Value |
|---|---|
| Total Duration | 18 months |
| Total Phases | 5 |
| Total Tasks | 32 |
| Recommended Team Size | 8–15 |
| Platform Type | SaaS, Computer Vision, MLOps |

---

## Phase 1 — Foundation
**Timeline:** Months 1–3  
**Theme:** Core infrastructure, auth, data ingestion, and basic project management.

| Task | Category | Stage | Description |
|---|---|---|---|
| Project setup & cloud infra | Infrastructure | Stage 1–2 | Provision cloud (AWS/GCP), set up CI/CD pipelines, Kubernetes, and staging environments. |
| Authentication & team management | Infrastructure | Stage 2–4 | SSO, RBAC roles (admin, annotator, reviewer, viewer), team workspaces, and API keys. |
| Dataset upload & storage | Data & Labeling | Stage 3–5 | Bulk image/video upload, S3 object storage integration, dataset versioning. |
| Basic annotation canvas (images) | Data & Labeling | Stage 4–8 | Bounding box, polygon, and classification tools on a web canvas. Keyboard shortcuts. |
| Project & dataset dashboard | Product | Stage 5–8 | Create/manage projects, dataset previews, annotation progress tracking. |
| REST API skeleton | Infrastructure | Stage 6–10 | Authenticated CRUD API for datasets, assets, and annotations. OpenAPI spec. |

**Deliverables:**
- Working cloud environment with CI/CD
- User auth and team RBAC system
- Basic image annotation canvas
- REST API with OpenAPI docs
- Project management dashboard

---

## Phase 2 — Labeling Engine
**Timeline:** Months 3–7  
**Theme:** Production-grade annotation tools, collaborative workflows, and quality control.

| Task | Category | Stage | Description |
|---|---|---|---|
| Segmentation & keypoint tools | Data & Labeling | Stage 9–14 | Polygon segmentation with auto-close, semantic & instance masks, keypoint skeletons. |
| AI-assisted auto-annotation | Data & Labeling | Stage 11–16 | Integrate SAM / Grounding DINO for smart click, box-prompt, and auto-label suggestions. |
| Video frame annotation & tracking | Data & Labeling | Stage 13–18 | Frame-by-frame labeling, object track propagation, RAFT/DeepSORT assisted tracking. |
| Review & approval workflow | Product | Stage 14–18 | Assign tasks to annotators, reviewer approval queue, issue flagging, comment threads. |
| Consensus & quality scoring | Data & Labeling | Stage 16–20 | Inter-annotator agreement (IoU, Cohen's κ), auto-reject low-confidence labels. |
| Label export (COCO, YOLO, Pascal VOC) | Data & Labeling | Stage 18–22 | Export in standard formats, custom field mapping, selective split generation. |
| 3D point cloud annotation (beta) | Data & Labeling | Stage 20–28 | WebGL-based 3D canvas, cuboid annotation, LiDAR data support. |

**Deliverables:**
- Full annotation toolset (box, polygon, segmentation, keypoint, 3D)
- AI-assisted labeling with SAM/Grounding DINO
- Video annotation with tracking
- Review and approval workflow
- Quality scoring and consensus tools
- Export in COCO, YOLO, Pascal VOC formats

> ⚠️ **Risk note:** This is the most engineering-intensive phase. AI-assisted annotation quality requires careful model integration. Budget additional time.

---

## Phase 3 — Training Platform
**Timeline:** Months 7–12  
**Theme:** No-code model training, experiment tracking, hyperparameter tuning, and evaluation.

| Task | Category | Stage | Description |
|---|---|---|---|
| Training pipeline engine | ML & Training | Stage 25–30 | Job queue (Ray / Celery), GPU scheduling, PyTorch/TensorFlow training runners. |
| Model architecture library | ML & Training | Stage 26–32 | Support YOLO, Faster R-CNN, EfficientDet, Mask R-CNN, ViT, SAM. Drag-and-drop builder. |
| Hyperparameter & augmentation UI | ML & Training | Stage 28–34 | Visual config for LR, batch size, epochs, augmentation pipeline (albumentations). |
| Experiment tracking dashboard | ML & Training | Stage 30–36 | Live loss/mAP curves, metric comparison across runs, artifact storage. |
| Transfer learning & fine-tuning | ML & Training | Stage 32–38 | Pre-trained weight hub (COCO, ImageNet), LoRA/adapter fine-tuning for VLMs. |
| Model evaluation & visualisation | ML & Training | Stage 36–42 | mAP, F1, confusion matrix, side-by-side prediction vs ground truth viewer. |
| AutoML & NAS (optional) | ML & Training | Stage 40–48 | Automated architecture search, Bayesian hyperparameter optimisation. |

**Deliverables:**
- GPU-backed training job queue
- No-code model builder (YOLO, Faster R-CNN, ViT, etc.)
- Hyperparameter and augmentation UI
- Experiment tracking with live metrics
- Transfer learning and fine-tuning support
- Model evaluation visualiser (mAP, F1, confusion matrix)

> ⚠️ **Cost note:** GPU spend spikes here. Plan cloud budgets or negotiate GPU partnerships (Lambda Labs, CoreWeave) before this phase starts.

---

## Phase 4 — Deployment & MLOps
**Timeline:** Months 12–15  
**Theme:** One-click cloud and edge deployment, inference API, monitoring, and feedback loops.

| Task | Category | Stage | Description |
|---|---|---|---|
| Model packaging & registry | Deploy & Ops | Stage 46–50 | ONNX/TensorRT export, versioned model registry, changelogs and rollback. |
| Cloud inference API | Deploy & Ops | Stage 48–54 | Auto-scaled REST/gRPC endpoints, JWT auth, rate limiting, SLA monitoring. |
| Edge deployment (IoT/on-prem) | Deploy & Ops | Stage 50–56 | Docker/Jetson/RPi packaging, OTA updates, offline inference support. |
| Production monitoring & drift | Deploy & Ops | Stage 52–58 | Real-time confidence tracking, data drift alerts, Grafana dashboards. |
| Active learning feedback loop | Deploy & Ops | Stage 54–60 | Flag low-confidence predictions back to labeling queue, auto-retraining triggers. |
| Security & compliance | Infrastructure | Stage 46–60 | SOC 2 prep, data locality controls, encryption at rest/in transit, audit logs. |

**Deliverables:**
- ONNX/TensorRT model registry with versioning
- Auto-scaled REST/gRPC inference API
- Edge deployment packages (Jetson, RPi, Docker)
- Production monitoring and drift detection
- Active learning loop back to labeling
- SOC 2 compliance foundation

> ⚠️ **Compliance note:** If targeting healthcare (HIPAA) or enterprise, begin SOC 2 audit process no later than the start of this phase — it takes 3–6 months.

---

## Phase 5 — Scale & Growth
**Timeline:** Months 15–18  
**Theme:** Multi-tenancy, marketplace, enterprise features, and go-to-market.

| Task | Category | Stage | Description |
|---|---|---|---|
| Multi-tenant SaaS billing | Product | Stage 61–66 | Stripe integration, usage-based billing, seat limits, enterprise contract support. |
| SDK & developer integrations | Infrastructure | Stage 62–68 | Python/JS SDK, CLI, Webhooks, Zapier/n8n connectors, full API docs. |
| Solutions & vertical templates | Product | Stage 64–70 | Pre-built pipelines for healthcare, manufacturing, retail, smart city verticals. |
| Community & marketplace | Product | Stage 66–72 | Shared model hub, annotation template library, public dataset integrations. |
| Performance & global scale | Infrastructure | Stage 68–72 | Multi-region CDN, DB sharding, queue-based annotation job distribution. |
| Enterprise onboarding & support | Product | Stage 70–72 | Dedicated CSM, SLA tiers, custom training, on-prem deployment option. |

**Deliverables:**
- Stripe-powered SaaS billing (usage-based + seat)
- Python/JS SDK and CLI
- Vertical solution templates (healthcare, retail, manufacturing, smart city)
- Model and annotation marketplace
- Multi-region global infrastructure
- Enterprise tier with dedicated support

---

## Recommended Team Composition

| Role | Phase(s) | Notes |
|---|---|---|
| Backend Engineer (2) | 1–5 | API, infra, storage, billing |
| Frontend Engineer (2) | 1–5 | Annotation canvas, dashboards, UI |
| ML Engineer (2) | 2–4 | AI-assist models, training engine, MLOps |
| DevOps / Platform Engineer (1) | 1–5 | CI/CD, Kubernetes, GPU scheduling |
| Data Engineer (1) | 2–3 | Dataset pipelines, export formats, versioning |
| Product Manager (1) | 1–5 | Roadmap, specs, customer research |
| QA Engineer (1) | 2–5 | Annotation quality, API testing |
| Growth / Developer Relations (1) | 5 | SDK docs, community, enterprise sales |

---

## Suggested Tech Stack

| Layer | Technology |
|---|---|
| Cloud | AWS / GCP (multi-region) |
| Container orchestration | Kubernetes (EKS / GKE) |
| CI/CD | GitHub Actions / ArgoCD |
| Backend | Python (FastAPI or Django) |
| Frontend | React + TypeScript |
| Annotation canvas | Fabric.js / Konva.js / custom WebGL |
| ML frameworks | PyTorch, TensorFlow, ONNX, TensorRT |
| Training jobs | Ray, Celery, Slurm |
| Storage | S3 (assets), PostgreSQL (metadata), Redis (queues) |
| Monitoring | Grafana, Prometheus, OpenTelemetry |
| Billing | Stripe |
| Auth | Auth0 / Keycloak |

---

## Key Risks & Mitigations

| Risk | Phase | Mitigation |
|---|---|---|
| AI-assisted annotation quality is poor | 2 | Pilot SAM/Grounding DINO on real customer data early; set fallback to manual |
| GPU costs exceed budget | 3 | Pre-negotiate spot instance credits; use Lambda Labs or CoreWeave as cost fallback |
| SOC 2 / HIPAA delays enterprise sales | 4 | Start compliance scoping at Month 12, engage auditor before Phase 4 ends |
| Annotation canvas performance with large images | 2 | Use tiled rendering and WebGL from the start; don't retrofit |
| Scope creep in labeling tooling | 2 | Timebox 3D annotation as beta; don't block Phase 3 on it |

---

*Generated for agent use — structured for parsing, task assignment, and project management integration.*
