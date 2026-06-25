# Training Infrastructure & GPU Deployment Plan

## 1. Hiện trạng

| Thành phần      | Backend (`visiox/training/`)                                    | Frontend (`visiox-ui/app/train/`)                  |
| --------------- | --------------------------------------------------------------- | -------------------------------------------------- |
| Models          | ✅ `ModelArchitecture`, `TrainingJob`, `Experiment`, `RunMetric` | ✅ `lib/api.ts` có đầy đủ types + methods           |
| Views           | ✅ CRUD endpoints + status transitions (`queued`, `cancelled`)   | ✅ Dashboard + `NewJobModal` + live metrics polling |
| Celery Task     | ⚠️ Mock (`sleep + random`)                                      | —                                                  |
| DL Dependencies | ❌ Chưa có PyTorch / TensorFlow / ONNX                           | —                                                  |
| GPU Support     | ❌ Docker chưa có CUDA                                           | —                                                  |
| Model Artifacts | ⚠️ `ModelRegistry` có `model_file` field                        | —                                                  |
| Dataset Export  | ✅ COCO / YOLO / VOC / Mask / Keypoints                          | —                                                  |

---

## 2. Kiến trúc đề xuất

```text
TrainingJob (status=pending)
    │ PATCH {"status":"queued"}
    ▼
Celery task → TrainingEngine.run()
    │
    ├── Dataset export (COCO/YOLO) → temp dir
    ├── Load model architecture (YOLOv8, Faster R-CNN, DETR...)
    ├── Train loop → stream metrics → RunMetric (DB)
    ├── Export best weights → .pt / .onnx / .tensorrt
    └── Auto-register vào ModelRegistry
         │
         ▼
    InferenceEndpoint có thể deploy
```

---

## 3. Các model Object Detection nên hỗ trợ trước

| Model            | Framework   | Ưu điểm                          |
| ---------------- | ----------- | -------------------------------- |
| YOLOv8 / YOLOv11 | Ultralytics | Dễ triển khai, hệ sinh thái mạnh |
| Faster R-CNN     | torchvision | Baseline kinh điển               |
| DETR             | HuggingFace | Transformer-based                |

### Giai đoạn 1: Chỉ hỗ trợ YOLOv8

Lý do:

* Codebase hiện tại đã hỗ trợ export YOLO.
* Thư viện Ultralytics cung cấp đầy đủ train/val/export.
* Dễ mở rộng thêm Faster R-CNN hoặc DETR sau này.

---

## 4. Implementation Plan

### Phase 1 — Backend Training Engine (5–7 ngày)

| Task | Mô tả                                                             |
| ---- | ----------------------------------------------------------------- |
| 1.1  | Thêm `torch`, `ultralytics`, `supervision` vào `requirements.txt` |
| 1.2  | Tạo package `training/engine/`                                    |
| 1.3  | Tạo `BaseTrainer` abstract class                                  |
| 1.4  | Implement `YOLOv8Trainer`                                         |
| 1.5  | Cập nhật `run_training_job` task                                  |
| 1.6  | Streaming metrics realtime                                        |
| 1.7  | Auto-register model sau khi train                                 |
| 1.8  | Dataset export tự động                                            |
| 1.9  | Hyperparameter validation                                         |
| 1.10 | Train / Val / Test split                                          |

### Phase 2 — GPU Infrastructure (2–3 ngày)

| Task | Mô tả                      |
| ---- | -------------------------- |
| 2.1  | Docker GPU worker          |
| 2.2  | Docker Compose GPU profile |
| 2.3  | Redis queue routing        |
| 2.4  | CPU fallback               |

### Phase 3 — Frontend Enhancements (3–4 ngày)

| Task | Mô tả                        |
| ---- | ---------------------------- |
| 3.1  | Architecture selector filter |
| 3.2  | Dynamic hyperparameter form  |
| 3.3  | Realtime metrics charts      |
| 3.4  | Download model               |
| 3.5  | Deploy trained model         |
| 3.6  | Training history             |

---

## 5. Luồng dữ liệu chi tiết

### Bước 1

User chọn:

* Project
* Dataset
* YOLOv8
* Epochs / Learning Rate / Batch Size

### Bước 2

Frontend:

```http
POST /api/v1/training-jobs/
```

Tạo `TrainingJob` với trạng thái:

```text
pending
```

### Bước 3

Frontend:

```http
PATCH status=queued
```

Celery task bắt đầu chạy.

### Bước 4

Export dataset:

```http
GET /api/datasets/{id}/export/?export_format=yolo&save_images=true
```

Giải nén:

```text
/tmp/visiox-training/{job_id}/
```

### Bước 5

Khởi tạo YOLOv8 với hyperparameters.

### Bước 6

Trong mỗi epoch:

* Ghi `RunMetric`
* Loss
* mAP50
* mAP75
* F1

Frontend poll:

```text
2 giây / lần
```

và render realtime chart.

### Bước 7

Sau khi train xong:

* Save `best.pt`
* Export ONNX
* Export TensorRT
* Upload artifact storage
* Tạo `ModelRegistry`
* Update:

```text
TrainingJob.status = completed
```

### Bước 8

User chọn:

```text
Deploy
```

→ tạo endpoint từ model vừa train.

---

## 6. Rủi ro & Lưu ý

### Model Artifacts

* YOLOv8 `.pt` ≈ 6 MB
* YOLOv8 `.onnx` ≈ 12 MB

Cần đảm bảo storage đủ dung lượng.

### Training Time

Training có thể kéo dài hàng giờ.

=> Nên tách Celery Worker riêng.

### GPU Memory

Cần:

* Giới hạn batch size
* Auto detect VRAM

### Concurrent Jobs

Sử dụng:

* Redis queue
* Concurrency limit

### Error Handling

Nếu task lỗi:

```text
status = failed
error_message = ...
```

Frontend hiển thị lỗi cho người dùng.

---

## 7. File Structure Mới

```text
visiox/training/
├── engine/
│   ├── __init__.py
│   ├── base.py
│   ├── yolo_v8.py
│   ├── faster_rcnn.py
│   └── registry.py
├── models.py
├── views/
│   └── training_view.py
├── serializers.py
├── urls.py
└── tasks.py
```

### Thay đổi chính

```text
tasks.py
```

Từ:

```text
mock training
```

Sang:

```text
dispatch → engine
```

---

# GPU Machine Deployment (192.168.210.26)

## Kiến trúc tổng thể

```text
┌─────────────────────────┐
│ Main Server             │
│ Django API :8000        │
│ PostgreSQL :5432        │
│ Redis :6379             │
│ Frontend :3000          │
└────────────┬────────────┘
             │ HTTP
             ▼
┌─────────────────────────┐
│ GPU Server              │
│ 192.168.210.26          │
│                         │
│ Training Agent :8001    │
│ Inference API :8002     │
│ CUDA GPU                │
└─────────────────────────┘
```

---

## Luồng Training

1. User bấm Start.
2. Django export dataset.
3. Django gọi:

```http
POST http://192.168.210.26:8001/v1/train
```

Payload:

```json
{
  "job_id": "...",
  "dataset_url": "...",
  "architecture": "yolov8",
  "hyperparams": {},
  "api_base_url": "...",
  "api_token": "..."
}
```

4. Training Agent:

   * Download dataset
   * Train model
   * Report metrics
   * Upload weights

5. Main Server:

   * Tạo `ModelRegistry`
   * Mark job completed

---

## Training Agent Structure

```text
gpu-training-agent/
├── requirements.txt
├── main.py
├── config.py
└── runners/
    ├── base.py
    └── yolo_v8.py
```

### API

```http
POST   /v1/train
DELETE /v1/train/{job_id}
```

---

## Inference Server Structure

```text
gpu-inference-server/
├── main.py
├── models/
├── requirements.txt
└── Dockerfile
```

### API

```http
POST /v1/predict/{model_id}
```

---

## Environment Variables

```env
GPU_AGENT_URL=http://192.168.210.26:8001
```

---

## Yêu cầu GPU Server

* Python 3.12
* CUDA Driver
* PyTorch CUDA
* Docker
* Mở port:

  * 8001 (Training)
  * 8002 (Inference)

---

## Kế hoạch triển khai

| Phase | Nội dung                |
| ----- | ----------------------- |
| 1     | Training Agent (YOLOv8) |
| 2     | Main Server Integration |
| 3     | Inference Server        |
| 4     | End-to-End Testing      |
