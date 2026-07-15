# VisioX — Database Schema

PostgreSQL schema, derived from the Django models in each app. Field types are the
PostgreSQL equivalents; every table has an implicit `id` BIGINT primary key unless
noted. `→` marks a foreign key and its `on_delete` behaviour.

> Generate the live picture anytime with `python manage.py showmigrations` /
> `python manage.py dbshell` (`\dt`, `\d <table>`).

---

## Apps → tables

| App | Tables |
| --- | --- |
| core | `core_usermodel` (auth user) |
| teams | `teams`, `team_members`, `team_invitations` |
| projects | `projects` |
| datasets | `datasets`, `media`, `media_label_profiles`, `augmentation_jobs` |
| annotations | `classes`, `annotations`, `labeling_tasks`, `job_issues`, `reviews` |
| training | `model_architectures`, `training_jobs`, `experiments`, `run_metrics` |
| deployments | `model_registry`, `inference_endpoints`, `monitoring_logs`, `drift_alerts` |
| billing | `plans`, `subscriptions`, `usage_records`, `api_keys`, `webhooks` |
| dataverse | `dataverse_projects` |

---

## ER overview (core domain)

```mermaid
erDiagram
    USER ||--o{ TEAM : owns
    USER ||--o{ TEAM_MEMBER : "is"
    TEAM ||--o{ TEAM_MEMBER : has
    TEAM ||--o{ TEAM_INVITATION : has
    TEAM ||--o{ PROJECT : "scopes (nullable)"
    USER ||--o{ PROJECT : owns
    PROJECT ||--o{ DATASET : has
    PROJECT ||--o{ CLASS : defines
    DATASET ||--o{ MEDIA : contains
    DATASET ||--o{ AUGMENTATION_JOB : tracks
    MEDIA ||--o| MEDIA_LABEL_PROFILE : "1:1"
    MEDIA ||--o{ ANNOTATION : has
    CLASS ||--o{ ANNOTATION : labels
    MEDIA ||--o{ LABELING_TASK : has
    ANNOTATION ||--o{ REVIEW : reviewed
    LABELING_TASK ||--o{ JOB_ISSUE : has
    PROJECT ||--o{ TRAINING_JOB : has
    DATASET ||--o{ TRAINING_JOB : "trains on"
    TRAINING_JOB ||--o{ EXPERIMENT : has
    EXPERIMENT ||--o{ RUN_METRIC : has
    TRAINING_JOB ||--o{ MODEL_REGISTRY : produces
    MODEL_REGISTRY ||--o{ INFERENCE_ENDPOINT : deploys
    INFERENCE_ENDPOINT ||--o{ MONITORING_LOG : logs
    INFERENCE_ENDPOINT ||--o{ DRIFT_ALERT : raises
    TEAM ||--o| SUBSCRIPTION : has
    PLAN ||--o{ SUBSCRIPTION : on
    PROJECT ||--o| DATAVERSE_PROJECT : "published as"
```

---

## core — `core_usermodel`
Custom user (`AUTH_USER_MODEL`), extends Django `AbstractUser` with no extra fields:
standard `username`, `email`, `password`, `is_staff`, `is_active`, `is_superuser`,
`date_joined`, `last_login`, plus the auth group/permission M2M tables.

---

## teams

### `teams`
| Column | Type | Notes |
| --- | --- | --- |
| name | varchar(255) | |
| owner_id | bigint | → user (CASCADE) |
| created_at | timestamptz | |

### `team_members`
| Column | Type | Notes |
| --- | --- | --- |
| team_id | bigint | → teams (CASCADE) |
| user_id | bigint | → user (CASCADE) |
| role | varchar(50) | owner / admin / member / viewer |
| joined_at | timestamptz | |
- **Unique:** (team, user)

### `team_invitations`
| Column | Type | Notes |
| --- | --- | --- |
| team_id | bigint | → teams (CASCADE) |
| email | varchar | |
| role | varchar(50) | admin / member / viewer |
| invited_by_id | bigint | → user (SET NULL) |
| token | uuid | unique |
| status | varchar(20) | pending / accepted / expired / cancelled |
| created_at, expires_at | timestamptz | default expiry +7 days |
- **Unique:** (team, email, status)

---

## projects — `projects`
| Column | Type | Notes |
| --- | --- | --- |
| team_id | bigint | → teams (SET NULL, nullable) |
| owner_id | bigint | → user (CASCADE, nullable) |
| name | varchar(255) | |
| task_type | varchar(100) | image_classification / object_detection / semantic_segmentation / instance_segmentation / keypoint_detection / video_annotation |
| description | text | nullable |
| created_at, updated_at | timestamptz | |

---

## datasets

### `datasets`
| Column | Type | Notes |
| --- | --- | --- |
| project_id | bigint | → projects (CASCADE) |
| name | varchar(255) | |
| description | text | nullable |
| version | integer | default 1 |
| verification_status | varchar(20) | `unverified` / `verified` |
| verified_by_id | bigint | nullable → core user (SET NULL) |
| verified_at | timestamptz | nullable |
| split_config | jsonb | generated/imported split configuration |
| split_updated_at | timestamptz | nullable |
| created_at, updated_at | timestamptz | |
- **Permissions:** `upload_media`, `export_dataset`

### `media`
| Column | Type | Notes |
| --- | --- | --- |
| dataset_id | bigint | → datasets (CASCADE) |
| type | varchar(50) | image / video |
| file | varchar(500) | storage path (raw/augmented/frames) |
| thumbnail | varchar(500) | nullable — precomputed gallery thumbnail path (`…/thumbs/`) |
| original_filename | varchar(255) | |
| width, height | integer | nullable |
| file_size | bigint | nullable |
| metadata | jsonb | e.g. `{"category": "augmented"}` |
| uploaded_at | timestamptz | |

### `media_label_profiles`
Per-image label roster (name/color overrides). One row per media.
| Column | Type | Notes |
| --- | --- | --- |
| media_id | bigint | → media (CASCADE), **OneToOne** |
| labels | jsonb | list of `{id, name, color}` |
| updated_at | timestamptz | |

### `augmentation_jobs`
Progress tracking for a background augmentation run (shared across workers).
| Column | Type | Notes |
| --- | --- | --- |
| dataset_id | bigint | → datasets (CASCADE) |
| status | varchar(20) | running / done / error |
| total | integer | planned copies |
| done | integer | processed (progress bar) |
| generated | integer | successfully created |
| error | text | nullable |
| created_at, updated_at | timestamptz | `updated_at` = heartbeat for stale detection |

### `dataset_import_jobs`
Persistent state for asynchronous image, YOLO26 and COCO imports.

| Column | Type | Notes |
| --- | --- | --- |
| dataset_id | bigint | → datasets (CASCADE) |
| format | varchar(20) | `images` / `yolo26` / `coco` |
| status | varchar(20) | `queued` / `running` / `done` / `error` |
| staged_files | jsonb | object descriptors in import staging |
| total | integer | total import items discovered |
| done | integer | items processed |
| summary | jsonb | final import counts/details |
| error | text | nullable, user-visible failure detail |
| created_by_id | bigint | nullable → core user (SET NULL) |
| created_at, updated_at | timestamptz | persistent progress timestamps |

---

## annotations

### `classes`
| Column | Type | Notes |
| --- | --- | --- |
| project_id | bigint | → projects (CASCADE) |
| name | varchar(255) | |
| color | varchar(7) | hex, default `#000000` |
| attributes | jsonb | |
| created_at | timestamptz | |
- **Unique:** (project, name)

### `annotations`
| Column | Type | Notes |
| --- | --- | --- |
| media_id | bigint | → media (CASCADE) |
| class_label_id | bigint | → classes (CASCADE) |
| annotator_id | bigint | → user (SET NULL) |
| type | varchar(50) | bbox / rectangle / polygon / polyline / point / keypoint / mask / cuboid / tag |
| data | jsonb | coordinates: `{x,y,width,height}` or `{points:[…]}` |
| frame | integer | video frame index; 0 for images |
| track_id | uuid | nullable — stable id across video frames |
| is_valid | boolean | default true |
| created_at, updated_at | timestamptz | |
- **Permissions:** `review_annotation`, `approve_annotation`

### `labeling_tasks`
| Column | Type | Notes |
| --- | --- | --- |
| media_id | bigint | → media (CASCADE) |
| assigned_to_id | bigint | → user (SET NULL, nullable) |
| status | varchar(50) | pending / in_progress / completed / review / approved / rejected |
| created_at, updated_at, completed_at | timestamptz | |

### `job_issues`
| Column | Type | Notes |
| --- | --- | --- |
| task_id | bigint | → labeling_tasks (CASCADE) |
| author_id | bigint | → user (SET NULL) |
| body | text | |
| created_at | timestamptz | |

### `reviews`
| Column | Type | Notes |
| --- | --- | --- |
| annotation_id | bigint | → annotations (CASCADE) |
| reviewer_id | bigint | → user (SET NULL) |
| status | varchar(50) | pending / approved / rejected / needs_revision |
| comment | text | nullable |
| reviewed_at, updated_at | timestamptz | |

---

## training

### `model_architectures`
| Column | Type | Notes |
| --- | --- | --- |
| name | varchar(255) | |
| backbone | varchar(255) | |
| task_type | varchar(100) | detection / classification / segmentation / keypoint |
| description | text | |
| default_config | jsonb | |
| is_builtin | boolean | default true |
| created_at | timestamptz | |

### `training_jobs`
| Column | Type | Notes |
| --- | --- | --- |
| project_id | bigint | → projects (CASCADE) |
| dataset_id | bigint | → datasets (SET NULL) |
| architecture_id | bigint | → model_architectures (SET NULL) |
| created_by_id | bigint | → user (SET NULL) |
| name | varchar(255) | |
| status | varchar(50) | pending / queued / running / completed / failed / cancelled |
| hyperparams, augmentation_config | jsonb | |
| celery_task_id | varchar(255) | |
| error_message | text | |
| started_at, finished_at, created_at, updated_at | timestamptz | |
- **Permissions:** `start_job`, `stop_job`

### `experiments`
| Column | Type | Notes |
| --- | --- | --- |
| job_id | bigint | → training_jobs (CASCADE) |
| name | varchar(255) | |
| notes | text | |
| created_at | timestamptz | |

### `run_metrics`
| Column | Type | Notes |
| --- | --- | --- |
| experiment_id | bigint | → experiments (CASCADE) |
| epoch, step | integer | |
| loss, val_loss, map50, map75, f1, accuracy | double | nullable |
| extra | jsonb | |
| recorded_at | timestamptz | |

---

## deployments

### `model_registry`
| Column | Type | Notes |
| --- | --- | --- |
| training_job_id | bigint | → training_jobs (SET NULL, nullable) |
| name | varchar(255) | |
| version | varchar(50) | default `1.0.0` |
| format | varchar(50) | pytorch / onnx / tensorrt / tflite / coreml |
| model_file | varchar | artifact path (`visiox-artifacts` bucket) |
| file_size | bigint | nullable |
| metrics | jsonb | |
| changelog | text | |
| created_by_id | bigint | → user (SET NULL) |
| created_at, updated_at | timestamptz | |

### `inference_endpoints`
| Column | Type | Notes |
| --- | --- | --- |
| registry_entry_id | bigint | → model_registry (CASCADE) |
| name | varchar(255) | |
| status | varchar(50) | inactive / starting / active / stopping / error |
| endpoint_url | varchar | |
| auth_token | varchar(64) | auto-generated |
| rate_limit_rpm | integer | default 100 |
| confidence_threshold | double | default 0.5 |
| created_by_id | bigint | → user (SET NULL) |
| created_at, updated_at | timestamptz | |
- **Permissions:** `start_endpoint`, `stop_endpoint`

### `monitoring_logs`
| Column | Type | Notes |
| --- | --- | --- |
| endpoint_id | bigint | → inference_endpoints (CASCADE) |
| confidence | double | |
| prediction | jsonb | |
| latency_ms | double | nullable |
| is_flagged | boolean | |
| flagged_reason | varchar(255) | |
| timestamp | timestamptz | |
- **Indexes:** (endpoint, timestamp), (is_flagged)

### `drift_alerts`
| Column | Type | Notes |
| --- | --- | --- |
| endpoint_id | bigint | → inference_endpoints (CASCADE) |
| severity | varchar(20) | low / medium / high / critical |
| metric | varchar(100) | |
| threshold, observed_value | double | |
| details | jsonb | |
| is_resolved | boolean | |
| created_at, resolved_at | timestamptz | |

---

## billing

### `plans`
| Column | Type | Notes |
| --- | --- | --- |
| name | varchar(100) | unique |
| description | text | |
| price_usd | numeric(10,2) | |
| billing_period | varchar(20) | monthly / annual |
| storage_gb, max_seats, gpu_hours_monthly | integer | |
| stripe_price_id | varchar(255) | |
| is_active | boolean | |
| created_at | timestamptz | |

### `subscriptions`
| Column | Type | Notes |
| --- | --- | --- |
| team_id | bigint | → teams (CASCADE), **OneToOne** |
| plan_id | bigint | → plans (PROTECT) |
| stripe_customer_id, stripe_subscription_id | varchar(255) | |
| status | varchar(50) | active / past_due / cancelled / trialing / incomplete |
| current_period_start/end, cancelled_at, created_at, updated_at | timestamptz | |

### `usage_records`
| Column | Type | Notes |
| --- | --- | --- |
| team_id | bigint | → teams (CASCADE) |
| type | varchar(50) | storage_gb / gpu_hours / api_requests / inference_calls |
| quantity | double | |
| stripe_usage_record_id | varchar(255) | |
| billed_at | timestamptz | |

### `api_keys`
| Column | Type | Notes |
| --- | --- | --- |
| user_id | bigint | → user (CASCADE) |
| team_id | bigint | → teams (CASCADE, nullable) |
| name | varchar(100) | |
| key_hash | varchar(64) | unique (SHA-256; raw key shown once) |
| prefix | varchar(8) | |
| is_active | boolean | |
| last_used, expires_at, created_at | timestamptz | nullable where applicable |

### `webhooks`
| Column | Type | Notes |
| --- | --- | --- |
| team_id | bigint | → teams (CASCADE) |
| url | varchar | |
| events | jsonb | subscribed event names |
| secret | varchar(64) | auto-generated |
| is_active | boolean | |
| created_at, updated_at | timestamptz | |

---

## dataverse — `dataverse_projects`
| Column | Type | Notes |
| --- | --- | --- |
| source_project_id | bigint | → projects (CASCADE), **OneToOne** |
| owner_id | bigint | → user (CASCADE) |
| title | varchar(255) | |
| summary | text | |
| tags | jsonb | list |
| license | varchar(100) | default `Community` |
| is_public | boolean | |
| fork_count, view_count | integer | |
| created_at, updated_at | timestamptz | |

---

## Delete-cascade summary (what disappears when you delete a row)

- **Project** → its datasets, classes, training jobs, dataverse listing.
- **Dataset** → its media, augmentation jobs, training-job link (SET NULL).
- **Media** → its annotations, label profile, labeling tasks, thumbnail row.
- **Class** → its annotations (so deleting a used class removes those boxes — the
  UI blocks this when `annotation_count > 0`).
- **Team** → members, invitations, subscription, usage, api keys, webhooks; its
  projects keep existing but `team_id` is set NULL.
- **User** → owned teams/projects cascade; authored annotations/reviews/issues are
  kept with the user field set NULL.
