# VisioX Platform — API Reference

Base URL: `http://localhost:8000`  
Default authentication: `Authorization: Bearer <access_token>` (JWT)  
Default content-type: `application/json`

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

---

## 1. Authentication

### POST `/api/auth/login/`
Đăng nhập bằng username/password, trả về JWT tokens.

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
Đăng ký tài khoản mới.

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
Vô hiệu hoá refresh token (blacklist).

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
Lấy thông tin user hiện tại.

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
Đăng nhập bằng OAuth (Google hoặc GitHub).

**Auth required:** No

**Request body:**
```json
{
  "provider": "google | github",
  "code": "string (authorization code từ OAuth provider)",
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
Làm mới access token bằng refresh token.

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
Lấy danh sách teams mà user là thành viên.

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
Tạo team mới. User tạo tự động trở thành owner và thành viên với role `owner`.

**Request body:**
```json
{
  "name": "string (required)"
}
```

**Response `201`:** Team object

---

### GET `/api/teams/{id}/`
Lấy chi tiết team.

**Response `200`:** Team object

---

### PUT `/api/teams/{id}/`
Cập nhật team (yêu cầu owner hoặc admin).

**Request body:**
```json
{
  "name": "string"
}
```

**Response `200`:** Team object

---

### DELETE `/api/teams/{id}/`
Xoá team. **Permission required:** `teams.delete_team`

**Response `204`:** No content

---

### GET `/api/teams/{id}/members/`
Lấy danh sách thành viên của team.

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
Mời user vào team. **Permission required:** `teams.invite_member` + owner/admin

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
Xoá thành viên khỏi team (không thể xoá owner).

**Response `204`:** No content

---

### PATCH `/api/teams/{id}/members/{member_id}/role/`
Cập nhật role của thành viên.

**Request body:**
```json
{
  "role": "admin | member | viewer"
}
```

**Response `200`:** TeamMember object

---

## 3. Projects

### GET `/api/projects/`
Lấy danh sách projects.

**Query params:**
- `search` — tìm theo tên hoặc description
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
    "thumbnail": "http://... (URL ảnh đầu tiên hoặc null)",
    "cvat_project_id": null,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/projects/`
Tạo project mới. User tự động trở thành owner.

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
Lấy chi tiết project.

---

### PUT `/api/projects/{id}/`
Cập nhật project.

**Request body:** Project fields (tất cả required)

---

### PATCH `/api/projects/{id}/`
Cập nhật một phần project.

---

### DELETE `/api/projects/{id}/`
Xoá project. **Permission required:** `projects.delete_project`

**Response `204`:** No content

---

## 4. Datasets

### GET `/api/datasets/`
Lấy danh sách datasets.

**Query params:**
- `project` — lọc theo project ID

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
    "thumbnail": "http://... hoặc null",
    "cvat_task_id": null,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/datasets/`
Tạo dataset mới.

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
Lấy chi tiết dataset.

---

### PUT `/api/datasets/{id}/`
Cập nhật dataset.

---

### DELETE `/api/datasets/{id}/`
Xoá dataset. **Permission required:** `datasets.delete_dataset`

**Response `204`:** No content

---

### GET `/api/datasets/{id}/media/`
Lấy danh sách media files trong dataset.

**Response `200`:**
```json
[
  {
    "id": 1,
    "dataset": 1,
    "type": "image | video",
    "file": "string (file path)",
    "file_url": "http://... (absolute URL)",
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
Upload một file vào dataset. **Content-Type:** `multipart/form-data`

**Permission required:** `datasets.upload_media`

**Request body (form-data):**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | File cần upload |
| `type` | string | Yes | `image` hoặc `video` |
| `metadata` | JSON | No | Metadata bổ sung |

**Response `201`:** Media object  
**Response `409`:** File đã tồn tại (trùng tên)

---

### POST `/api/datasets/{id}/upload-batch/`
Upload nhiều files cùng lúc (tối đa 100). **Content-Type:** `multipart/form-data`

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
Xoá nhiều media files.

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
Lấy thống kê dataset (bao gồm CVAT task info).

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
Lấy dữ liệu CVAT browser (frames, labels, annotations).

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
Lấy ảnh của frame theo số thứ tự (0-based).

**Query params:**
- `token` — JWT token (cho `<img>` tags)
- `quality` — `compressed` hoặc `original` (CVAT mode)

**Auth required:** No (dùng `?token=` query param)  
**Response `200`:** Binary image data

---

### GET `/api/datasets/{id}/frames/{frame_num}/annotations/`
Lấy annotations của frame.

**Response `200`:** Array of Annotation objects

---

### PUT `/api/datasets/{id}/frames/{frame_num}/annotations/`
Lưu annotations cho frame (ghi đè toàn bộ).

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
Lấy URL để mở annotation trực tiếp trong CVAT.

**Response `200`:**
```json
{
  "url": "http://cvat.example.com/tasks/123"
}
```

---

### POST `/api/datasets/{id}/sync_cvat/`
Đồng bộ annotations từ CVAT về database.

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
Tăng version của dataset.

**Response `200`:** Updated Dataset object

---

### POST `/api/datasets/repair-cvat/`
Sửa các datasets bị mất liên kết CVAT task.

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
Nhận webhook events từ CVAT. **Auth required:** No

**Request body:**
```json
{
  "event": "create:task | delete:task | update:task | update:job",
  "task": { "id": 123, "name": "string", "project_id": 1 },
  "job": { "task_id": 123 }
}
```

---

### GET `/api/datasets/{dataset_id}/export/`
Export annotations sang định dạng khác.

**Query params:**
- `format` — `coco` (default), `yolo`, `voc`

**Response `200`:** Binary file (JSON hoặc ZIP)

---

## 5. Annotations

### GET `/api/classes/`
Lấy danh sách class labels.

**Query params:**
- `project` — lọc theo project ID

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
Tạo class label mới.

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
Lấy chi tiết class.

---

### PUT/PATCH `/api/classes/{id}/`
Cập nhật class.

---

### DELETE `/api/classes/{id}/`
Xoá class.

**Response `204`:** No content

---

### GET `/api/annotations/`
Lấy danh sách annotations (lọc theo team membership).

**Query params:**
- `media` — lọc theo media ID
- `type` — lọc theo loại annotation

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
    "track_id": "uuid hoặc null",
    "is_valid": true,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/annotations/`
Tạo một annotation.

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
Tạo nhiều annotations cùng lúc.

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
Xoá nhiều annotations.

**Request body:**
```json
{
  "ids": [1, 2, 3]
}
```

**Response `204`:** No content

---

### GET `/api/media/{media_id}/annotations/`
Lấy tất cả annotations của một media item.

**Response `200`:** Array of Annotation objects

---

### PUT `/api/media/{media_id}/annotations/`
Lưu annotations cho media (ghi đè toàn bộ — full snapshot).

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
Lấy label profile (danh sách labels đang dùng) của media.

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
Lưu label profile cho media.

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
Lấy label profile của frame.

**Response `200`:** `{ "labels": [...] }`

---

### PUT `/api/datasets/{dataset_id}/frames/{frame_num}/label-profile/`
Lưu label profile cho frame.

**Request body:** `{ "labels": [...] }`

**Response `200`:** `{ "labels": [...] }`

---

### GET `/api/media/{media_id}/quality/`
Lấy metrics chất lượng annotation (inter-annotator agreement) cho một media.

**Response `200`:**
```json
{
  "cohens_kappa": 0.85,
  "mean_iou": 0.92
}
```

---

### GET `/api/datasets/{dataset_id}/quality/`
Lấy metrics chất lượng tổng hợp cho toàn dataset.

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

### GET `/api/tasks/` hoặc `/api/jobs/`
Lấy danh sách labeling tasks.

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
Tạo labeling task.

**Request body:**
```json
{
  "media": 1
}
```

**Response `201`:** LabelingTask object

---

### GET `/api/tasks/{id}/annotations/`
Lấy annotations của task.

**Response `200`:** Array of Annotation objects

---

### PATCH `/api/tasks/{id}/annotations/`
Lưu annotations cho task.

**Request body:**
```json
{
  "annotations": [...]
}
```

**Response `200`:** Array of Annotation objects

---

### GET `/api/tasks/{id}/issues/`
Lấy danh sách issues của task.

**Response `200`:**
```json
[
  {
    "id": 1,
    "task": 1,
    "author": 1,
    "author_username": "string",
    "body": "Bounding box không chính xác",
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### POST `/api/tasks/{id}/issues/`
Tạo issue cho task.

**Request body:**
```json
{
  "body": "string (required)"
}
```

**Response `201`:** JobIssue object

---

### POST `/api/tasks/{id}/start/`
Bắt đầu task (pending → in_progress), gán cho user hiện tại.

**Response `200`:** Updated LabelingTask object

---

### POST `/api/tasks/{id}/complete/`
Hoàn thành task (in_progress → completed).

**Response `200`:** Updated LabelingTask object

---

### POST `/api/tasks/{id}/submit_for_review/`
Gửi task để review (completed → review).

**Response `200`:** Updated LabelingTask object

---

### POST `/api/tasks/{id}/approve/`
Phê duyệt task (review → approved).

**Response `200`:** Updated LabelingTask object

---

### POST `/api/tasks/{id}/reject/`
Từ chối task (review → rejected).

**Response `200`:** Updated LabelingTask object

---

### GET `/api/reviews/`
Lấy danh sách reviews.

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
Tạo review cho annotation. Reviewer tự động là user hiện tại.

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
Phê duyệt review.

**Response `200`:** Updated Review object (`status: "approved"`)

---

### POST `/api/reviews/{id}/reject/`
Từ chối review.

**Request body:**
```json
{
  "comment": "string (optional)"
}
```

**Response `200`:** Updated Review object (`status: "rejected"`)

---

### POST `/api/reviews/{id}/request_revision/`
Yêu cầu sửa lại.

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
Lấy danh sách model architectures.

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
Tạo architecture mới. **Permission required:** Admin only

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
Lấy danh sách training jobs.

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
Tạo training job mới.

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
Bắt đầu training job (enqueue Celery task). **Permission required:** `training.start_job`

**Response `200`:** Updated TrainingJob object (`status: "queued"`)

---

### POST `/api/training-jobs/{id}/stop/`
Dừng training job. **Permission required:** `training.start_job`

**Response `200`:** Updated TrainingJob object (`status: "cancelled"`)

---

### GET `/api/training-jobs/{id}/experiments/`
Lấy danh sách experiments của training job.

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
Lấy tất cả experiments.

---

### GET `/api/experiments/{id}/metrics/`
Lấy metrics theo epoch của experiment.

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
Lấy danh sách model registry.

**Response `200`:**
```json
[
  {
    "id": 1,
    "training_job": 1,
    "name": "YOLOv8 v1.0",
    "version": 1,
    "format": "onnx | pytorch | tensorflow",
    "model_file": "http://...",
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
Đăng ký model mới. **Content-Type:** `multipart/form-data`

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
Rollback về version trước.

**Response `200`:**
```json
{
  "message": "Rolled back to version 1",
  "active_version": { ...ModelRegistry object... }
}
```

---

### GET `/api/endpoints/`
Lấy danh sách inference endpoints.

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
Tạo inference endpoint mới. Auth token tự động được tạo.

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
Kích hoạt endpoint. **Permission required:** `deployments.start_endpoint`

**Response `200`:** Updated endpoint (`status: "active"`)

---

### POST `/api/endpoints/{id}/stop/`
Dừng endpoint. **Permission required:** `deployments.stop_endpoint`

**Response `200`:** Updated endpoint (`status: "inactive"`)

---

### POST `/api/endpoints/{id}/log_prediction/`
Ghi log một lần inference.

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
Lấy 100 logs gần nhất.

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
Lấy danh sách drift alerts chưa được giải quyết.

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
Kích hoạt drift check (Celery task).

**Response `200`:**
```json
{
  "task_id": "celery-task-uuid",
  "message": "Drift check started"
}
```

---

### GET `/api/monitoring/`
Lấy tất cả monitoring logs.

---

### GET `/api/drift-alerts/`
Lấy tất cả drift alerts.

---

### PATCH `/api/drift-alerts/{id}/`
Cập nhật drift alert.

---

### POST `/api/drift-alerts/{id}/resolve/`
Đánh dấu alert đã được giải quyết.

**Response `200`:** Updated DriftAlert object (`is_resolved: true`, `resolved_at` set)

---

## 8. Billing

### GET `/api/plans/`
Lấy danh sách plans.

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
Đăng ký plan cho team (tích hợp Stripe).

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
Lấy subscription hiện tại.

**Query params:**
- `team_id` — lọc theo team

**Response `200`:** Subscription object

---

### POST `/api/subscriptions/cancel/`
Huỷ subscription.

**Request body:**
```json
{
  "team_id": 1
}
```

**Response `204`:** No content

---

### GET `/api/usage/`
Lấy danh sách usage records của team.

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
Lấy danh sách API keys.

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
Tạo API key mới. **Full key chỉ hiển thị một lần khi tạo.**

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
Thu hồi API key.

**Response `204`:** No content

---

### GET `/api/webhooks/`
Lấy danh sách webhooks.

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
Tạo webhook mới.

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
Cập nhật webhook.

---

### DELETE `/api/webhooks/{id}/`
Xoá webhook.

**Response `204`:** No content

---

### POST `/api/webhooks/{id}/test/`
Gửi test event đến webhook.

**Response `200`:**
```json
{
  "task_id": "celery-task-uuid",
  "message": "Test webhook dispatched"
}
```

---

### POST `/api/webhooks/stripe/`
Stripe webhook endpoint (xác thực bằng `Stripe-Signature` header).

**Auth required:** No

---

## 9. Dataverse

### GET `/api/dataverse/`
Lấy danh sách public projects trong Dataverse.

**Query params:**
- `search` — tìm theo title, summary, tags
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
    "thumbnail": "http://... hoặc null",
    "fork_count": 12,
    "view_count": 340,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

---

### GET `/api/dataverse/{id}/`
Lấy chi tiết public project. Tự động tăng `view_count`.

**Response `200`:** DataverseProject object

---

### POST `/api/dataverse/share-project/`
Chia sẻ project lên Dataverse.

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
Fork một public project vào team của mình. Sao chép toàn bộ classes, datasets, media và annotations.

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
|--------|---------|
| `400` | Validation error — response body chứa chi tiết lỗi |
| `401` | Chưa xác thực hoặc token hết hạn |
| `403` | Không có quyền truy cập |
| `404` | Không tìm thấy resource |
| `409` | Conflict (ví dụ: file đã tồn tại) |
| `500` | Server error |

**Ví dụ lỗi validation `400`:**
```json
{
  "email": ["This field is required."],
  "password": ["Ensure this field has at least 8 characters."]
}
```

**Ví dụ lỗi `404`:**
```json
{
  "detail": "Not found."
}
```
