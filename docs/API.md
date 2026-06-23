# VisioX Platform — API Reference

Base URL: `http://localhost:8000`

**Authentication methods:**

| Method | Header | Notes |
|---|---|---|
| JWT Bearer | `Authorization: Bearer <access_token>` | Default. Access token expires in 1 hour. |
| API Key | `X-API-KEY: <raw key>` | Programmatic access. Key shown once at creation. |

> **Frame image endpoints** (`/api/datasets/{id}/frames/{n}/`) use `AllowAny` — no auth required. Pass the URL directly into `<img src>` without headers or tokens.

Default content-type: `application/json`

**Interactive docs:** `http://localhost:8000/api/docs/` (Swagger) · `http://localhost:8000/api/redoc/`

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Teams](#2-teams)
3. [Projects](#3-projects)
4. [Datasets](#4-datasets)
5. [Annotations](#5-annotations)
6. [Training](#6-training)
7. [Deployments](#7-deployments)
8. [Billing](#8-billing)
9. [Dataverse](#9-dataverse)
10. [Error Responses](#error-responses)

---

## 1. Authentication

### POST `/api/auth/login/`
Login with username/password, returns JWT tokens.

**Auth required:** No

**Request body:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response `200`:**
```json
{
  "user_id": 1,
  "username": "string",
  "email": "user@example.com",
  "first_name": "string",
  "last_name": "string",
  "access_token": "string",
  "refresh_token": "string"
}
```

---

### POST `/api/auth/register/`
Register a new account.

**Auth required:** No

**Request body:**
```json
{
  "username": "string (required, max 150 chars)",
  "email": "user@example.com (required)",
  "password": "string (required, min 8 chars)",
  "first_name": "string (optional)",
  "last_name": "string (optional)"
}
```

**Response `201`:**
```json
{
  "user_id": 1,
  "username": "string",
  "email": "user@example.com",
  "created_at": "2024-01-01T00:00:00Z"
}
```

---

### POST `/api/auth/logout/`
Invalidate the refresh token (blacklist).

**Auth required:** No

**Request body:**
```json
{
  "refresh_token": "string"
}
```

**Response `204`:** No content

---

### GET `/api/auth/me/`
Get current user information.

**Auth required:** Yes

**Response `200`:**
```json
{
  "user_id": 1,
  "username": "string",
  "email": "user@example.com",
  "first_name": "string",
  "last_name": "string",
  "is_staff": false
}
```

---

### POST `/api/auth/oauth/`
Login via OAuth (Google or GitHub).

**Auth required:** No

**Request body:**
```json
{
  "provider": "google | github",
  "code": "string (authorization code from OAuth provider)",
  "redirect_uri": "http://localhost:3000/auth/callback"
}
```

**Response `200`:**
```json
{
  "user_id": 1,
  "email": "user@example.com",
  "first_name": "string",
  "last_name": "string",
  "access_token": "string",
  "refresh_token": "string"
}
```

---

### POST `/api/auth/token/refresh/`
Refresh the access token using a refresh token.

**Auth required:** No

**Request body:**
```json
{
  "refresh": "string"
}
```

**Response `200`:**
```json
{
  "access": "string (new access token)"
}
```

---

## 2. Teams

### GET `/api/teams/`
Get list of teams the current user is a member of.

**Response `200`:**
```json
[
  {
    "id": 1,
    "name": "string",
    "owner": 1,
    "owner_username": "string",
    "member_count": 5,
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/teams/`
Create a new team. The creator is automatically set as owner with role `owner`.

**Request body:**
```json
{
  "name": "string (required)"
}
```

**Response `201`:** Team object

---

### GET `/api/teams/{id}/`
Get team details.

**Response `200`:** Team object

---

### PUT `/api/teams/{id}/`
Update team (requires owner or admin role).

**Request body:**
```json
{
  "name": "string"
}
```

**Response `200`:** Team object

---

### DELETE `/api/teams/{id}/`
Delete team. **Permission required:** `teams.delete_team`

**Response `204`:** No content

---

### GET `/api/teams/{id}/members/`
Get the list of team members.

**Response `200`:**
```json
[
  {
    "id": 1,
    "user": 1,
    "user_username": "string",
    "user_email": "user@example.com",
    "role": "owner | admin | member | viewer",
    "joined_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/teams/{id}/invite/`
Invite a user to the team. **Permission required:** `teams.invite_member` + owner/admin

**Request body:**
```json
{
  "username": "string (required)",
  "role": "admin | member | viewer (optional, default: member)"
}
```

**Response `201`:** TeamMember object

---

### DELETE `/api/teams/{id}/members/{member_id}/`
Remove a member from the team (cannot remove the owner).

**Response `204`:** No content

---

### PATCH `/api/teams/{id}/members/{member_id}/role/`
Update a member's role.

**Request body:**
```json
{
  "role": "admin | member | viewer"
}
```

**Response `200`:** TeamMember object

---

### POST `/api/teams/{id}/send_invitation/`
Send an email invitation to a new user (without an existing account). **Permission required:** owner/admin

**Request body:**
```json
{
  "email": "newuser@example.com (required)",
  "role": "admin | member | viewer (optional, default: member)"
}
```

**Response `201`:**
```json
{
  "id": 1,
  "team": 1,
  "email": "newuser@example.com",
  "role": "member",
  "status": "pending",
  "expires_at": "2024-01-08T00:00:00Z",
  "created_at": "2024-01-01T00:00:00Z"
}
```

---

### GET `/api/teams/{id}/invitations/`
Get the list of invitations (pending + expired) for the team.

**Response `200`:** Array of Invitation objects

---

### DELETE `/api/teams/{id}/invitations/{invite_id}/`
Cancel an invitation.

**Response `204`:** No content

---

### GET `/api/invitations/{token}/accept/`
Accept an invitation via the token in the email. **Auth required:** No (link-based)

**Response `200`:**
```json
{
  "team_id": 1,
  "team_name": "Computer Vision Team",
  "role": "member"
}
```

**Response `400`:** Invitation expired or already used

---

## 3. Projects

### GET `/api/projects/`
Get list of projects.

**Query params:**
- `search` — search by name or description
- `ordering` — `created_at`, `updated_at`, `name`

**Response `200`:**
```json
[
  {
    "id": 1,
    "team": 1,
    "team_name": "string",
    "owner": 1,
    "owner_username": "string",
    "owner_email": "user@example.com",
    "name": "string",
    "task_type": "image_classification | object_detection | semantic_segmentation | instance_segmentation | keypoint_detection | video_annotation",
    "description": "string",
    "thumbnail": "http://... (presigned MinIO URL of first image, or null)",
    "cvat_project_id": null,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/projects/`
Create a new project. The creator is automatically set as owner.

**Request body:**
```json
{
  "team": 1,
  "name": "string (required, min 3 chars)",
  "task_type": "object_detection",
  "description": "string (optional)"
}
```

**Response `201`:** Project object

---

### GET `/api/projects/{id}/`
Get project details.

---

### PUT `/api/projects/{id}/`
Update project.

**Request body:** Project fields (all required)

---

### PATCH `/api/projects/{id}/`
Partially update a project.

---

### DELETE `/api/projects/{id}/`
Delete project. **Permission required:** `projects.delete_project`

**Response `204`:** No content

---

## 4. Datasets

### GET `/api/datasets/`
Get list of datasets.

**Query params:**
- `project` — filter by project ID

**Response `200`:**
```json
[
  {
    "id": 1,
    "project": 1,
    "name": "string",
    "description": "string",
    "version": 1,
    "media_count": 100,
    "thumbnail": "http://... (presigned MinIO URL or null)",
    "cvat_task_id": null,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/datasets/`
Create a new dataset.

**Request body:**
```json
{
  "project": 1,
  "name": "string",
  "description": "string (optional)"
}
```

**Response `201`:** Dataset object

---

### GET `/api/datasets/{id}/`
Get dataset details.

---

### PUT `/api/datasets/{id}/`
Update dataset.

---

### DELETE `/api/datasets/{id}/`
Delete dataset. **Permission required:** `datasets.delete_dataset`

**Response `204`:** No content

---

### GET `/api/datasets/{id}/media/`
Get list of media files in a dataset.

**Response `200`:**
```json
[
  {
    "id": 1,
    "dataset": 1,
    "type": "image | video",
    "file": "string (MinIO object key, e.g. orgs/1_my-team/projects/1_my-project/datasets/1_dataset/v1/raw/photo.jpg)",
    "file_url": "http://... (presigned MinIO URL valid ~1 hour; or /media/... path when USE_MINIO=False)",
    "original_filename": "photo.jpg",
    "width": 1920,
    "height": 1080,
    "file_size": 204800,
    "metadata": {},
    "uploaded_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/datasets/{id}/upload/`
Upload a single file to a dataset. **Content-Type:** `multipart/form-data`

**Permission required:** `datasets.upload_media`

**Request body (form-data):**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | File to upload |
| `type` | string | Yes | `image` or `video` |
| `metadata` | JSON | No | Additional metadata |

**Response `201`:** Media object  
**Response `409`:** File already exists (duplicate name)

---

### POST `/api/datasets/{id}/upload-batch/`
Upload multiple files at once (max 100). **Content-Type:** `multipart/form-data`

**Permission required:** `datasets.upload_media`

**Request body (form-data):**
| Field | Type | Required |
|-------|------|----------|
| `files` | file[] | Yes |
| `type` | string | Yes |
| `metadata` | JSON | No |

**Response `201`:** Array of Media objects

---

### POST `/api/datasets/{id}/delete-media/`
Delete multiple media files.

**Permission required:** `datasets.upload_media`

**Request body:**
```json
{
  "media_ids": [1, 2, 3]
}
```

**Response `200`:**
```json
{
  "deleted": 3,
  "ids": [1, 2, 3]
}
```

---

### GET `/api/datasets/{id}/stats/`
Get dataset statistics (including CVAT task info).

**Response `200`:**
```json
{
  "id": 1,
  "name": "string",
  "version": 1,
  "project_id": 1,
  "project_name": "string",
  "cvat_task_id": null,
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z",
  "cvat": null
}
```

---

### GET `/api/datasets/{id}/browser/`
Get CVAT browser data (frames, labels, annotations).

**Response `200`:**
```json
{
  "dataset_id": 1,
  "dataset_name": "string",
  "version": 1,
  "frames": [],
  "labels": [],
  "annotations": []
}
```

---

### GET `/api/datasets/{id}/frames/{frame_num}/`
Get the image for a frame by index (0-based).

**Query params:**
- `token` — JWT token (for `<img>` tags)
- `quality` — `compressed` or `original` (CVAT mode)

**Auth required:** No (use `?token=` query param)  
**Response `200`:** Binary image data

---

### GET `/api/datasets/{id}/frames/{frame_num}/annotations/`
Get annotations for a frame.

**Response `200`:** Array of Annotation objects

---

### PUT `/api/datasets/{id}/frames/{frame_num}/annotations/`
Save annotations for a frame (full overwrite).

**Request body:**
```json
{
  "annotations": [
    {
      "class_label": 1,
      "type": "rectangle | polygon | polyline | points | cuboid | tag",
      "data": { "x": 10, "y": 20, "width": 100, "height": 50 },
      "frame": 0,
      "track_id": "uuid (optional)"
    }
  ]
}
```

**Response `200`:** Array of Annotation objects

---

### GET `/api/datasets/{id}/annotate_url/`
Get URL to open the dataset directly in CVAT for annotation.

**Response `200`:**
```json
{
  "url": "http://cvat.example.com/tasks/123"
}
```

---

### POST `/api/datasets/{id}/sync_cvat/`
Sync annotations from CVAT to the database.

**Response `200`:**
```json
{
  "status": "synced",
  "version": 2,
  "cvat_status": "string",
  "total_labels": 50
}
```

---

### POST `/api/datasets/{id}/new_version/`
Increment the dataset version.

**Response `200`:** Updated Dataset object

---

### POST `/api/datasets/repair-cvat/`
Repair datasets that lost their CVAT task link.

**Response `200`:**
```json
{
  "status": "ok",
  "repaired_count": 2,
  "repaired": [1, 5]
}
```

---

### POST `/api/datasets/cvat-webhook/`
Receive webhook events from CVAT. **Auth required:** No

**Request body:**
```json
{
  "event": "create:task | delete:task | update:task | update:job",
  "task": { "id": 123, "name": "string", "project_id": 1 },
  "job": { "task_id": 123 }
}
```

---

### GET `/api/v1/datasets/{dataset_id}/export/`
Export annotations to other formats.

**Query params:**
- `export_format` — `coco` (default), `yolo`, `voc`, `mask`, `coco_keypoints`, `imagenet`
- `save_images` — include source images in the ZIP (`true`/`false`, default `false`)

The legacy `format` query parameter remains supported for compatibility.

**Response `200`:** ZIP archive (`application/zip`)

---

## 5. Annotations

### GET `/api/classes/`
Get list of class labels.

**Query params:**
- `project` — filter by project ID

**Response `200`:**
```json
[
  {
    "id": 1,
    "project": 1,
    "name": "car",
    "color": "#ef4444",
    "attributes": {},
    "annotation_count": 42,
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/classes/`
Create a new class label.

**Request body:**
```json
{
  "project": 1,
  "name": "car",
  "color": "#ef4444 (optional)",
  "attributes": {} 
}
```

**Response `201`:** Class object

---

### GET `/api/classes/{id}/`
Get class details.

---

### PUT/PATCH `/api/classes/{id}/`
Update class.

---

### DELETE `/api/classes/{id}/`
Delete class.

**Response `204`:** No content

---

### GET `/api/annotations/`
Get list of annotations (filtered by team membership).

**Query params:**
- `media` — filter by media ID
- `type` — filter by annotation type

**Response `200`:**
```json
[
  {
    "id": 1,
    "media": 1,
    "class_label": 1,
    "class_name": "car",
    "annotator": 1,
    "annotator_username": "string",
    "type": "rectangle | polygon | polyline | points | cuboid | tag",
    "data": {},
    "frame": 0,
    "track_id": "uuid or null",
    "is_valid": true,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/annotations/`
Create a single annotation.

**Request body:**
```json
{
  "media": 1,
  "class_label": 1,
  "type": "rectangle",
  "data": { "x": 10, "y": 20, "width": 100, "height": 50 },
  "frame": 0,
  "track_id": "uuid (optional)"
}
```

**Response `201`:** Annotation object

---

### POST `/api/annotations/bulk/`
Create multiple annotations at once.

**Request body:**
```json
{
  "annotations": [
    { "media": 1, "class_label": 1, "type": "rectangle", "data": {} }
  ]
}
```

**Response `201`:** Array of Annotation objects

---

### DELETE `/api/annotations/bulk-delete/`
Delete multiple annotations.

**Request body:**
```json
{
  "ids": [1, 2, 3]
}
```

**Response `204`:** No content

---

### GET `/api/media/{media_id}/annotations/`
Get all annotations for a media item.

**Response `200`:** Array of Annotation objects

---

### PUT `/api/media/{media_id}/annotations/`
Save annotations for a media item (full overwrite — snapshot).

**Request body:**
```json
{
  "annotations": [
    {
      "class_label": 1,
      "type": "rectangle",
      "data": { "x": 10, "y": 20, "width": 100, "height": 50 },
      "frame": 0,
      "track_id": null
    }
  ]
}
```

**Response `200`:** Array of Annotation objects

---

### GET `/api/media/{media_id}/label-profile/`
Get label profile (list of labels in use) for a media item.

**Response `200`:**
```json
{
  "labels": [
    { "id": 1, "name": "car", "color": "#ef4444" }
  ]
}
```

---

### PUT `/api/media/{media_id}/label-profile/`
Save label profile for a media item.

**Request body:**
```json
{
  "labels": [
    { "id": 1, "name": "car", "color": "#ef4444" }
  ]
}
```

**Response `200`:** `{ "labels": [...] }`

---

### GET `/api/datasets/{dataset_id}/frames/{frame_num}/label-profile/`
Get label profile for a frame.

**Response `200`:** `{ "labels": [...] }`

---

### PUT `/api/datasets/{dataset_id}/frames/{frame_num}/label-profile/`
Save label profile for a frame.

**Request body:** `{ "labels": [...] }`

**Response `200`:** `{ "labels": [...] }`

---

### GET `/api/media/{media_id}/quality/`
Get annotation quality metrics (inter-annotator agreement) for a media item.

**Response `200`:**
```json
{
  "cohens_kappa": 0.85,
  "mean_iou": 0.92
}
```

---

### GET `/api/datasets/{dataset_id}/quality/`
Get aggregated annotation quality metrics for an entire dataset.

**Response `200`:**
```json
{
  "dataset_id": 1,
  "media_count": 100,
  "average_iou": 0.91,
  "average_cohens_kappa": 0.84,
  "per_media": [
    { "media_id": 1, "iou": 0.93, "cohens_kappa": 0.88 }
  ]
}
```

---

### GET `/api/tasks/` or `/api/jobs/`
Get list of labeling tasks.

**Query params:**
- `status` — `pending | in_progress | completed | review | approved | rejected`

**Response `200`:**
```json
[
  {
    "id": 1,
    "media": 1,
    "media_url": "http://...",
    "assigned_to": 1,
    "assigned_to_username": "string",
    "status": "pending",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
    "completed_at": null
  }
]
```

---

### POST `/api/tasks/`
Create a labeling task.

**Request body:**
```json
{
  "media": 1
}
```

**Response `201`:** LabelingTask object

---

### GET `/api/tasks/{id}/annotations/`
Get annotations for a task.

**Response `200`:** Array of Annotation objects

---

### PATCH `/api/tasks/{id}/annotations/`
Save annotations for a task.

**Request body:**
```json
{
  "annotations": [...]
}
```

**Response `200`:** Array of Annotation objects

---

### GET `/api/tasks/{id}/issues/`
Get list of issues for a task.

**Response `200`:**
```json
[
  {
    "id": 1,
    "task": 1,
    "author": 1,
    "author_username": "string",
    "body": "Bounding box is inaccurate",
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/tasks/{id}/issues/`
Create an issue for a task.

**Request body:**
```json
{
  "body": "string (required)"
}
```

**Response `201`:** JobIssue object

---

### POST `/api/tasks/{id}/start/`
Start a task (pending → in_progress), assigned to the current user.

**Response `200`:** Updated LabelingTask object

---

### POST `/api/tasks/{id}/complete/`
Complete a task (in_progress → completed).

**Response `200`:** Updated LabelingTask object

---

### POST `/api/tasks/{id}/submit_for_review/`
Submit a task for review (completed → review).

**Response `200`:** Updated LabelingTask object

---

### POST `/api/tasks/{id}/approve/`
Approve a task (review → approved).

**Response `200`:** Updated LabelingTask object

---

### POST `/api/tasks/{id}/reject/`
Reject a task (review → rejected).

**Response `200`:** Updated LabelingTask object

---

### GET `/api/reviews/`
Get list of reviews.

**Query params:**
- `status` — `pending | approved | rejected | needs_revision`

**Response `200`:**
```json
[
  {
    "id": 1,
    "annotation": 1,
    "reviewer": 1,
    "reviewer_username": "string",
    "status": "pending",
    "comment": "string",
    "reviewed_at": null,
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/reviews/`
Create a review for an annotation. The reviewer is automatically set to the current user.

**Request body:**
```json
{
  "annotation": 1,
  "status": "pending (optional)",
  "comment": "string (optional)"
}
```

**Response `201`:** Review object

---

### POST `/api/reviews/{id}/approve/`
Approve a review.

**Response `200`:** Updated Review object (`status: "approved"`)

---

### POST `/api/reviews/{id}/reject/`
Reject a review.

**Request body:**
```json
{
  "comment": "string (optional)"
}
```

**Response `200`:** Updated Review object (`status: "rejected"`)

---

### POST `/api/reviews/{id}/request_revision/`
Request revision.

**Request body:**
```json
{
  "comment": "string (optional)"
}
```

**Response `200`:** Updated Review object (`status: "needs_revision"`)

---

## 6. Training

### GET `/api/architectures/`
Get list of model architectures.

**Response `200`:**
```json
[
  {
    "id": 1,
    "name": "YOLOv8",
    "backbone": "CSPDarknet",
    "task_type": "object_detection | image_classification | semantic_segmentation | instance_segmentation | keypoint_detection",
    "description": "string",
    "default_config": {},
    "is_builtin": true,
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/architectures/`
Create a new architecture. **Permission required:** Admin only

**Request body:**
```json
{
  "name": "string",
  "task_type": "object_detection",
  "backbone": "string (optional)",
  "description": "string (optional)",
  "default_config": {}
}
```

**Response `201`:** ModelArchitecture object

---

### GET `/api/training-jobs/`
Get list of training jobs.

**Response `200`:**
```json
[
  {
    "id": 1,
    "project": 1,
    "dataset": 1,
    "architecture": 1,
    "architecture_name": "YOLOv8",
    "created_by": 1,
    "created_by_username": "string",
    "name": "Training Run #1",
    "status": "pending | queued | running | completed | failed | cancelled",
    "hyperparams": { "epochs": 100, "lr": 0.001 },
    "augmentation_config": {},
    "error_message": null,
    "started_at": null,
    "finished_at": null,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
    "experiment_count": 0
  }
]
```

---

### POST `/api/training-jobs/`
Create a new training job.

**Request body:**
```json
{
  "project": 1,
  "dataset": 1,
  "architecture": 1,
  "name": "string",
  "hyperparams": { "epochs": 100, "lr": 0.001 },
  "augmentation_config": {}
}
```

**Response `201`:** TrainingJob object

---

### POST `/api/training-jobs/{id}/start/`
Start a training job (enqueue Celery task). **Permission required:** `training.start_job`

**Response `200`:** Updated TrainingJob object (`status: "queued"`)

---

### POST `/api/training-jobs/{id}/stop/`
Stop a training job. **Permission required:** `training.start_job`

**Response `200`:** Updated TrainingJob object (`status: "cancelled"`)

---

### GET `/api/training-jobs/{id}/experiments/`
Get list of experiments for a training job.

**Response `200`:**
```json
[
  {
    "id": 1,
    "job": 1,
    "name": "Experiment 1",
    "notes": "string",
    "metrics": [],
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### GET `/api/experiments/`
Get all experiments.

---

### GET `/api/experiments/{id}/metrics/`
Get per-epoch metrics for an experiment.

**Response `200`:**
```json
[
  {
    "id": 1,
    "experiment": 1,
    "epoch": 1,
    "step": 100,
    "loss": 0.25,
    "val_loss": 0.30,
    "map50": 0.75,
    "map75": 0.55,
    "f1": 0.82,
    "accuracy": null,
    "extra": {},
    "recorded_at": "2024-01-01T00:00:00Z"
  }
]
```

---

## 7. Deployments

### GET `/api/registry/`
Get list of model registry entries.

**Response `200`:**
```json
[
  {
    "id": 1,
    "training_job": 1,
    "name": "YOLOv8 v1.0",
    "version": 1,
    "format": "onnx | pytorch | tensorflow",
    "model_file": "http://... (presigned URL from visiox-artifacts MinIO bucket; path: training-jobs/{job_id}/weights/{filename})",
    "file_size": 52428800,
    "metrics": { "map50": 0.85 },
    "changelog": "Initial release",
    "created_by": 1,
    "created_by_username": "string",
    "endpoint_count": 2,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/registry/`
Register a new model. **Content-Type:** `multipart/form-data`

**Request body (form-data):**
| Field | Type | Required |
|-------|------|----------|
| `training_job` | integer | Yes |
| `name` | string | Yes |
| `format` | string | Yes |
| `model_file` | file | Yes |
| `metrics` | JSON | No |
| `changelog` | string | No |

**Response `201`:** ModelRegistry object

---

### POST `/api/registry/{id}/rollback/`
Roll back to the previous version.

**Response `200`:**
```json
{
  "message": "Rolled back to version 1",
  "active_version": { "...ModelRegistry object..." : null }
}
```

---

### GET `/api/endpoints/`
Get list of inference endpoints.

**Response `200`:**
```json
[
  {
    "id": 1,
    "registry_entry": 1,
    "name": "Production API",
    "status": "active | inactive",
    "endpoint_url": "http://inference.example.com/predict",
    "auth_token": "****abcd",
    "rate_limit_rpm": 100,
    "confidence_threshold": 0.7,
    "created_by": 1,
    "created_by_username": "string",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/endpoints/`
Create a new inference endpoint. Auth token is generated automatically.

**Request body:**
```json
{
  "registry_entry": 1,
  "name": "string",
  "endpoint_url": "http://...",
  "rate_limit_rpm": 100,
  "confidence_threshold": 0.7
}
```

**Response `201`:** InferenceEndpoint object

---

### POST `/api/endpoints/{id}/start/`
Activate endpoint. **Permission required:** `deployments.start_endpoint`

**Response `200`:** Updated endpoint (`status: "active"`)

---

### POST `/api/endpoints/{id}/stop/`
Stop endpoint. **Permission required:** `deployments.stop_endpoint`

**Response `200`:** Updated endpoint (`status: "inactive"`)

---

### POST `/api/endpoints/{id}/log_prediction/`
Log a single inference event.

**Request body:**
```json
{
  "confidence": 0.92,
  "prediction": { "class": "car", "bbox": [10, 20, 100, 150] },
  "latency_ms": 45.2
}
```

**Response `201`:** MonitoringLog object

---

### GET `/api/endpoints/{id}/logs/`
Get the 100 most recent logs.

**Response `200`:**
```json
[
  {
    "id": 1,
    "endpoint": 1,
    "confidence": 0.92,
    "prediction": {},
    "latency_ms": 45.2,
    "is_flagged": false,
    "flagged_reason": null,
    "timestamp": "2024-01-01T00:00:00Z"
  }
]
```

---

### GET `/api/endpoints/{id}/alerts/`
Get list of unresolved drift alerts.

**Response `200`:**
```json
[
  {
    "id": 1,
    "endpoint": 1,
    "severity": "low | medium | high",
    "metric": "confidence",
    "threshold": 0.7,
    "observed_value": 0.55,
    "details": {},
    "is_resolved": false,
    "created_at": "2024-01-01T00:00:00Z",
    "resolved_at": null
  }
]
```

---

### POST `/api/endpoints/{id}/trigger_drift_check/`
Trigger a drift check (Celery task).

**Response `200`:**
```json
{
  "task_id": "celery-task-uuid",
  "message": "Drift check started"
}
```

---

### GET `/api/monitoring/`
Get all monitoring logs.

---

### GET `/api/drift-alerts/`
Get all drift alerts.

---

### PATCH `/api/drift-alerts/{id}/`
Update a drift alert.

---

### POST `/api/drift-alerts/{id}/resolve/`
Mark an alert as resolved.

**Response `200`:** Updated DriftAlert object (`is_resolved: true`, `resolved_at` set)

---

## 8. Billing

### GET `/api/plans/`
Get list of plans.

**Response `200`:**
```json
[
  {
    "id": 1,
    "name": "Pro",
    "description": "string",
    "price_usd": "49.00",
    "billing_period": "monthly | annual",
    "storage_gb": 100,
    "max_seats": 10,
    "gpu_hours_monthly": 50,
    "is_active": true,
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/subscriptions/subscribe/`
Subscribe a team to a plan (Stripe integration).

**Request body:**
```json
{
  "team_id": 1,
  "plan_id": 1
}
```

**Response `201`:**
```json
{
  "id": 1,
  "team": 1,
  "team_name": "string",
  "plan": 1,
  "plan_name": "Pro",
  "status": "active",
  "current_period_start": "2024-01-01T00:00:00Z",
  "current_period_end": "2024-02-01T00:00:00Z",
  "cancelled_at": null,
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

---

### GET `/api/subscriptions/my_subscription/`
Get the current subscription.

**Query params:**
- `team_id` — filter by team

**Response `200`:** Subscription object

---

### POST `/api/subscriptions/cancel/`
Cancel subscription.

**Request body:**
```json
{
  "team_id": 1
}
```

**Response `204`:** No content

---

### GET `/api/usage/`
Get usage records for the team.

**Response `200`:**
```json
[
  {
    "id": 1,
    "team": 1,
    "type": "storage | gpu_hours | seats",
    "quantity": 25.5,
    "billed_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### GET `/api/api-keys/`
Get list of API keys.

**Response `200`:**
```json
[
  {
    "id": 1,
    "name": "My API Key",
    "prefix": "vx_sk_ab",
    "team": 1,
    "is_active": true,
    "last_used": "2024-01-01T00:00:00Z",
    "expires_at": null,
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/api-keys/`
Create a new API key. **The full key is shown only once at creation.**

**Request body:**
```json
{
  "name": "string (required)",
  "team_id": 1,
  "expires_at": "2025-01-01T00:00:00Z (optional)"
}
```

**Response `201`:**
```json
{
  "id": 1,
  "name": "string",
  "key": "vx_sk_abcdefghijklmnop... (full key, shown once only)",
  "prefix": "vx_sk_ab",
  "is_active": true,
  "created_at": "2024-01-01T00:00:00Z"
}
```

---

### POST `/api/api-keys/{id}/revoke/`
Revoke an API key.

**Response `204`:** No content

---

### GET `/api/webhooks/`
Get list of webhooks.

**Response `200`:**
```json
[
  {
    "id": 1,
    "team": 1,
    "url": "https://example.com/webhook",
    "events": ["annotation.created", "job.completed"],
    "is_active": true,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/webhooks/`
Create a new webhook.

**Request body:**
```json
{
  "team": 1,
  "url": "https://example.com/webhook",
  "events": ["annotation.created"],
  "is_active": true
}
```

**Response `201`:** Webhook object

---

### PUT/PATCH `/api/webhooks/{id}/`
Update webhook.

---

### DELETE `/api/webhooks/{id}/`
Delete webhook.

**Response `204`:** No content

---

### POST `/api/webhooks/{id}/test/`
Send a test event to the webhook.

**Response `200`:**
```json
{
  "task_id": "celery-task-uuid",
  "message": "Test webhook dispatched"
}
```

---

### POST `/api/webhooks/stripe/`
Stripe webhook endpoint (validated via `Stripe-Signature` header).

**Auth required:** No

---

## 9. Dataverse

### GET `/api/dataverse/`
Get list of public projects in Dataverse.

**Query params:**
- `search` — search by title, summary, or tags
- `ordering` — `updated_at`, `created_at`, `fork_count`, `view_count`, `title`

**Response `200`:**
```json
[
  {
    "id": 1,
    "source_project": 1,
    "owner": 1,
    "owner_username": "string",
    "team_name": "string",
    "title": "Traffic Detection Dataset",
    "summary": "string",
    "tags": ["autonomous", "traffic"],
    "license": "Community",
    "is_public": true,
    "task_type": "object_detection",
    "dataset_count": 3,
    "media_count": 1500,
    "class_count": 10,
    "thumbnail": "http://... (presigned MinIO URL or null)",
    "fork_count": 12,
    "view_count": 340,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### GET `/api/dataverse/{id}/`
Get public project details. Automatically increments `view_count`.

**Response `200`:** DataverseProject object

---

### POST `/api/dataverse/share-project/`
Share a project to Dataverse.

**Request body:**
```json
{
  "project": 1,
  "title": "string (optional, default: project name)",
  "summary": "string (optional)",
  "tags": ["tag1", "tag2"],
  "license": "Community (optional)",
  "is_public": true
}
```

**Response `201`:** DataverseProject object

---

### POST `/api/dataverse/{id}/fork/`
Fork a public project into your team. Copies all classes, datasets, media, and annotations.

**Request body:**
```json
{
  "team": 1,
  "name": "string (optional, default: 'ProjectName Fork')"
}
```

**Response `201`:**
```json
{
  "project_id": 42,
  "name": "Traffic Detection Dataset Fork"
}
```

---

## Error Responses

| Status | Meaning |
|---|---|
| `400` | Validation error — response body contains per-field error details |
| `401` | Unauthenticated or token expired |
| `403` | Forbidden — insufficient permissions |
| `404` | Resource not found |
| `409` | Conflict (e.g. file already exists in the dataset) |
| `422` | Unprocessable entity — invalid data |
| `500` | Server error — check Django logs |

**Validation error `400` example:**
```json
{
  "email": ["This field is required."],
  "password": ["Ensure this field has at least 8 characters."]
}
```

**`401` error example:**
```json
{
  "detail": "Authentication credentials were not provided."
}
```

**`404` error example:**
```json
{
  "detail": "Not found."
}
```

---

## Pagination

All list endpoints support pagination (`PageNumberPagination`, default page size: 20).

**Query params:**
- `?page=<n>` — page number (starts at 1)
- `?page_size=<n>` — items per page (max: typically 100)

**Response structure:**
```json
{
  "count": 150,
  "next": "http://localhost:8000/api/datasets/?page=2",
  "previous": null,
  "results": [...]
}
```

---

## Webhook Events

Events are sent via outbound webhooks (`POST /api/webhooks/`) with header `X-Visiox-Signature: <HMAC-SHA256>`.

| Event | Trigger |
|---|---|
| `training.job.completed` | TrainingJob → completed |
| `training.job.failed` | TrainingJob → failed |
| `deployment.endpoint.started` | InferenceEndpoint → active |
| `deployment.endpoint.stopped` | InferenceEndpoint → inactive |
| `deployment.drift_alert.created` | DriftAlert created |
| `billing.subscription.updated` | Subscription status changed |
| `annotation.task.approved` | LabelingTask → approved |
| `annotation.task.rejected` | LabelingTask → rejected |

**Verify signature:**
```python
import hmac, hashlib

def verify_signature(payload_body: bytes, secret: str, signature_header: str) -> bool:
    expected = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)
```
