# Auto Label trong Annotation Editor

Tài liệu này định nghĩa kế hoạch thêm Auto Label vào native annotation editor,
bao gồm bounding box và instance segmentation. Trang mục tiêu:

```text
/datasets/{dataset_id}/annotate/native?mode=simple&frame={frame}
```

## 1. Mục tiêu

- Chạy Auto Label engine theo background job trên toàn bộ ảnh của dataset bằng
  model YOLO do người dùng import.
- Hỗ trợ bounding box và instance segmentation dạng polygon.
- Đưa kết quả vào editor dưới dạng draft để người dùng review.
- Cho phép sửa, xóa, Undo và Save bằng workflow annotation hiện tại.
- Không tự động xóa hoặc ghi đè annotation thủ công.
- Không gửi MinIO credentials xuống trình duyệt.

Semantic segmentation dạng bitmap mask không thuộc MVP vì editor hiện chưa có
mask renderer hoặc công cụ chỉnh sửa mask. Có thể bổ sung sau khi polygon
segmentation hoạt động ổn định.

## 2. Trạng thái hiện tại

Frontend đã hỗ trợ:

- Rectangle và polygon trong Konva editor.
- Chuyển đổi API `bbox`/`polygon` sang `EditorShape`.
- Draft theo frame, Undo/Redo và lưu annotation.
- Native frame URL, frame annotation và label profile.

Backend đã hỗ trợ:

- Model registry cho model được train từ project và kết nối Inference Agent.
- Dataset inference trả prediction chưa lưu.
- Dataset labeling ghi bounding box vào PostgreSQL.
- Annotation types `bbox`, `rectangle`, `polygon` và `mask`.

Khoảng trống cần xử lý:

- Inference contract hiện chỉ chuẩn hóa bounding box.
- Native annotation route làm việc theo frame, trong khi inference hiện nhận
  `media_ids`.
- Model registry chưa công bố rõ capability detection/segmentation.
- Editor chưa có Auto Label action và metadata dành cho model prediction.

`Run Model` và `Auto Label` là hai tính năng khác nhau:

| Tính năng | Nguồn model | Mục đích |
| --- | --- | --- |
| Run Model | Model được train từ project và lưu trong `ModelRegistry` | Chạy model project trên dataset |
| Auto Label | Model người dùng import hoặc managed provider như YOLO World | Tạo draft annotation trong editor |

Không dùng tên, API hoặc UI của `Run Model` cho Auto Label.

## 3. Quyết định kiến trúc

Auto Label mặc định chạy toàn dataset và lưu model annotation theo batch. Manual
annotation luôn được giữ; chạy lại chỉ thay output của cùng Auto Label model.

```text
Auto Label action
    -> Django tạo AutoLabelDatasetJob
    -> datasets worker chia toàn bộ Media theo batch
    -> Inference Agent tải ảnh/model và dự đoán
    -> worker map class có sẵn + lưu annotation
    -> frontend poll tiến độ và refresh frame hiện tại
    -> người dùng review/edit bằng annotation editor
```

Lợi ích:

- Dùng chung selection, object list, history và save flow.
- Không giữ HTTP request/UI mở trong suốt quá trình xử lý dataset lớn.
- Tiến độ và kết quả không mất khi API/worker restart.
- Không cần xây prediction overlay thứ hai cho việc review.

## 4. Auto Label source và capability

Auto Label có hai source ban đầu:

### 4.1 Imported model

Người dùng upload YOLO artifact, ví dụ `.pt`, rồi hệ thống kiểm tra và đăng ký
thành `AutoLabelModel`. Đây không phải `ModelRegistry` của training workflow.

Metadata tối thiểu:

- `name` và version tùy chọn.
- `framework`/`family`, ban đầu là `ultralytics`/`yolo`.
- `task_type`: `object_detection` hoặc `instance_segmentation`.
- `capabilities`: `bbox`, `polygon` hoặc cả hai nếu adapter hỗ trợ.
- Class names lấy từ model hoặc file metadata đi kèm.
- Artifact storage key, checksum, file size và validation status.
- Project/owner và người tạo.

Imported YOLO detection chỉ tạo bbox. Imported YOLO segmentation có thể tạo
polygon và có thể trả thêm bbox bao quanh instance nếu UI yêu cầu.

Model upload được kiểm tra phần mở rộng/kích thước/checksum và lưu vào artifact
storage. Django không import hoặc thực thi file PyTorch `.pt` vì artifact này có
thể chứa serialized Python object. Agent là nơi duy nhất được phép load model;
lỗi không tương thích được trả rõ khi chạy lần đầu.

### 4.2 Managed provider: YOLO World

YOLO World là provider được hệ thống quản lý. Người dùng không upload weights mà
chọn model variant và truyền text prompts. Prompts mặc định lấy từ project
classes nhưng có thể chỉnh sửa trước khi chạy.

YOLO World trực tiếp trả bounding box. Để tạo polygon cần một segmentation
refiner, ví dụ pipeline `YOLO World -> SAM`. Trong MVP:

- YOLO World: bật Bounding boxes.
- Segmentation polygons: chỉ bật khi provider khai báo capability `polygon`.
- Nếu chưa có refiner, UI disable Polygon và hiển thị lý do rõ ràng.

### 4.3 Khả năng mở rộng

API và database không dùng enum chỉ chứa tên YOLO. Mỗi source/provider công bố
capability và parameter schema:

```json
{
  "provider": "yolo_world",
  "display_name": "YOLO World",
  "capabilities": ["bbox"],
  "parameters": {
    "prompts": {"type": "string[]", "required": true},
    "confidence": {"type": "number", "min": 0, "max": 1}
  }
}
```

Provider registry sau này có thể thêm SAM, Grounding DINO, Detectron2 hoặc một
service riêng mà không thay đổi editor save flow. Frontend render form dựa trên
capabilities/parameter schema, còn backend validate lại toàn bộ request.

## 5. Django API cho frame inference

Endpoint đề xuất:

```http
POST /api/v1/datasets/{dataset_id}/frames/{frame}/predict/
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request khi dùng imported model:

```json
{
  "source": {
    "kind": "uploaded_model",
    "model_id": 12
  },
  "output_type": "bbox",
  "confidence": 0.45,
  "create_missing_classes": false
}
```

Request khi dùng YOLO World:

```json
{
  "source": {
    "kind": "provider",
    "provider": "yolo_world",
    "model": "yolov8s-worldv2",
    "prompts": ["person", "forklift", "pallet"]
  },
  "output_type": "bbox",
  "confidence": 0.45,
  "create_missing_classes": false
}
```

`source.kind` là discriminator chung, không phụ thuộc framework. `output_type`
nhận `bbox` hoặc `polygon`; source được chọn phải công bố capability tương ứng.
`confidence` phải nằm trong `[0, 1]`.

Response:

```json
{
  "dataset": 32,
  "frame": 0,
  "media_id": 4546,
  "source": {
    "kind": "uploaded_model",
    "model_id": 12,
    "provider": "ultralytics"
  },
  "predictions": [
    {
      "type": "bbox",
      "class_label": 12,
      "label": "person",
      "confidence": 0.91,
      "data": {
        "x": 80,
        "y": 40,
        "width": 120,
        "height": 300
      }
    },
    {
      "type": "polygon",
      "class_label": 12,
      "label": "person",
      "confidence": 0.88,
      "data": {
        "points": [100, 40, 150, 45, 180, 100]
      }
    }
  ],
  "created_classes": [],
  "unmapped_labels": []
}
```

Endpoint phải:

- Kiểm tra quyền truy cập dataset/project và imported model nếu có.
- Resolve frame thành đúng original `Media`.
- Resolve source thông qua provider registry.
- Từ chối source không hỗ trợ output được yêu cầu.
- Không ghi annotation vào PostgreSQL.
- Không trả storage credentials.
- Trả `400` cho request không hợp lệ, `404` cho dataset/frame/model không tồn
  tại, `409` cho capability conflict và `502` khi Inference Agent lỗi.

Mặc định không tự tạo class. Khi `create_missing_classes=true`, backend tạo
class theo quyền hiện tại và trả danh sách `created_classes` để frontend cập
nhật label roster.

## 6. Inference Agent contract

Django gửi request tới Inference Agent:

```json
{
  "engine": {
    "provider": "uploaded_yolo",
    "model_id": 12,
    "name": "person-segment",
    "version": "1.0.0",
    "format": "pytorch",
    "task_type": "instance_segmentation",
    "storage_key": "auto-label/models/12/model.pt",
    "checksum": "<sha256>"
  },
  "dataset": {
    "id": 32,
    "media_ids": [4546]
  },
  "output_type": "polygon",
  "confidence": 0.45
}
```

YOLO World request dùng cùng endpoint nhưng engine khác:

```json
{
  "engine": {
    "provider": "yolo_world",
    "model": "yolov8s-worldv2",
    "prompts": ["person", "forklift", "pallet"]
  },
  "dataset": {
    "id": 32,
    "media_ids": [4546]
  },
  "output_type": "bbox",
  "confidence": 0.45
}
```

Quy tắc output:

- Detection trả bbox `xywh` theo center coordinates hoặc `xyxy`.
- Segmentation trả polygon pixel từ output mask của model.
- Response phải khai báo `normalized` và format tọa độ.
- Agent thực hiện confidence filtering và NMS trước khi trả kết quả.
- Polygon phải có ít nhất ba điểm hợp lệ.
- Nên simplify polygon và giới hạn khoảng 256 vertices/object để tránh payload
  lớn và giảm chi phí render Konva.

Không trả mask PNG/base64 trong MVP.

Inference Agent triển khai adapter interface chung:

```text
AutoLabelProvider
├── UploadedYoloProvider
├── YoloWorldProvider
├── YoloWorldSamProvider        # phase sau
└── OtherProvider               # mở rộng
```

Mỗi adapter chịu trách nhiệm load/cache model, validate parameters và chuyển
output riêng của framework về prediction schema chung. Django và frontend không
import thư viện YOLO hoặc chứa logic phụ thuộc Ultralytics.

Dataset Auto Label mặc định gửi 32 ảnh/request. Inference Agent phải cache model
theo `checksum` (fallback `storage_key`), warmup một lần và tái sử dụng model
giữa các request của cùng job. Confidence mặc định của frontend/backend là
`0.45`.

## 7. Backend implementation

Vì Auto Label có lifecycle/model source khác `Run Model`, nên tạo domain riêng
thay vì tiếp tục mở rộng `deployments` ViewSet:

```text
auto_label/
├── models.py                   # AutoLabelModel
├── serializers.py
├── urls.py
├── views.py
├── services/
│   ├── inference.py
│   └── model_validation.py
└── providers/
    ├── base.py
    ├── uploaded_model.py
    └── yolo_world.py
```

Service chịu trách nhiệm:

- Resolve imported model hoặc managed provider.
- Tạo payload chung gọi agent.
- Validate response.
- Chuẩn hóa bbox và polygon.
- Clamp tọa độ theo kích thước ảnh.
- Map tên class không phân biệt hoa thường.
- Trả annotation draft thống nhất cho frontend.

Các converter đề xuất:

```text
prediction_bbox_data(prediction, media)
prediction_polygon_data(prediction, media)
prediction_to_annotation_draft(prediction, media, class_map)
```

Các converter hình học có thể được dùng lại bởi `predict-dataset` và
`label-dataset`, nhưng model catalog và permission của Auto Label vẫn tách khỏi
project training registry.

API quản lý imported model đề xuất:

```text
GET    /api/v1/auto-label/models/
POST   /api/v1/auto-label/models/
GET    /api/v1/auto-label/models/{id}/
DELETE /api/v1/auto-label/models/{id}/
GET    /api/v1/auto-label/providers/
POST   /api/v1/datasets/{dataset_id}/frames/{frame_num}/propagate/
GET    /api/v1/datasets/{dataset_id}/propagation-jobs/{job_id}/
```

Upload hợp lệ trả trạng thái `ready` sau khi Django kiểm tra metadata cơ bản và
lưu artifact. Trạng thái `validating`/`failed` được giữ trong schema để bổ sung
agent-side validation bất đồng bộ sau này; model chưa `ready` không được chạy.

### Propagate một object sang các frame sau

Workspace cho phép chọn một bounding box đã vẽ và chạy visual tracker không phụ
thuộc YOLO. Request gửi class, bbox nguồn, ngưỡng tương đồng mặc định `0.70` và
giới hạn frame tùy chọn. Celery worker trên queue `datasets` đọc ảnh từ
filesystem/MinIO, tìm object theo template đa tỉ lệ, bỏ qua bbox trùng với
annotation hiện có và lưu các kết quả với cùng một `track_id`.

Job tiếp tục chạy khi người dùng đóng dialog. Frontend poll endpoint job để hiển
thị số frame đã quét, số frame match và số annotation đã lưu.

## 8. Frontend implementation

Thêm `Auto Label` vào workspace header, không thêm vào drawing toolbar vì đây là
async action chứ không phải canvas tool.

UI mặc định được giữ tối giản cho annotation theo frame:

- Chọn phạm vi `Current frame` (mặc định, trả prediction về draft) hoặc
  `Entire dataset` (chạy background job và lưu kết quả theo từng frame).
- Chọn model đã import hoặc upload trực tiếp một file `.pt`.
- Tên model tự lấy từ tên file; version/task/class không bắt người dùng nhập.
- Class được phát hiện từ prediction của model và chỉ map theo tên vào class đã
  có trong project. Class không tồn tại bị bỏ qua, không tự tạo.
- Confidence và output chỉ hiện khi cần; Polygon chỉ hiện với model có capability
  segmentation.
- Prediction được append vào draft và người dùng review trước khi Save.
- Trong lúc frame đang tải hoặc dialog đang inference, không ghi draft rỗng,
  không Save và không điều hướng bằng phím tắt sang frame khác.

Provider như YOLO World vẫn tồn tại trong provider registry/API nhưng không hiển
thị trong dialog tối giản. Có thể đưa lại bằng một entry point riêng khi workflow
provider hoàn thiện, không làm phức tạp flow upload model thông thường.

Imported model form:

- Model selector chỉ hiển thị model `ready`.
- Nút `Import model` mở dialog upload riêng.
- Hiển thị framework, task, capabilities, class count và validation status.
- Output tự giới hạn theo capabilities của model.

YOLO World form:

- Model variant.
- Prompt chips, mặc định lấy từ project labels.
- Confidence.
- Chỉ bật output được provider hỗ trợ.
- Polygon bị disable cho tới khi pipeline segmentation refiner sẵn sàng.

Component đề xuất:

```text
components/annotate/AutoLabelDialog.tsx
components/annotate/ImportAutoLabelModelDialog.tsx
lib/annotation/useAutoLabel.ts
```

Mở rộng `EditorShape`:

```ts
type EditorShape = {
  // existing fields
  source?: "manual" | "imported" | "auto_label";
  confidence?: number;
  autoLabelSource?: "uploaded_model" | "provider";
  autoLabelModelId?: number;
  autoLabelProvider?: string;
  autoLabelEngineName?: string;
};
```

Mapper phải:

- Chuyển prediction `bbox` thành `rectangle`.
- Chuyển prediction `polygon` thành polygon shape.
- Giữ `source`, `confidence`, `auto_label_source`, `auto_label_model_id` hoặc
  `auto_label_provider` khi Save/reload.
- Thêm cả prediction batch bằng một lần cập nhật `AnnotationSession`.

Request phải có `AbortController` hoặc request ID. Nếu người dùng chuyển frame
trước khi request hoàn thành, kết quả cũ phải bị hủy hoặc bỏ qua, không được chèn
vào frame mới.

## 9. UX và trạng thái

Auto Label cần đầy đủ các trạng thái:

- Chưa import model.
- Model đang upload/validating/failed/ready.
- Không có imported model tương thích với output đã chọn.
- Đang tải model và provider catalog.
- YOLO World chưa có prompt.
- Provider không hỗ trợ Polygon.
- Đang inference.
- Thành công nhưng không có prediction.
- Có label chưa map.
- Agent timeout/offline.
- Prediction đã thêm vào draft nhưng chưa Save.

Object list nên hiển thị badge `AI`, confidence và tên model. Prediction draft có
thể dùng nét đứt; sau khi Save/reload hiển thị giống annotation bình thường.

Manual annotation không được xóa bởi merge strategy. `Replace` chỉ xóa Auto
Label draft có cùng engine identity (imported model ID hoặc provider/model
variant) trên frame hiện tại.

## 10. Kiểm thử

Backend unit/API tests:

- Resolve đúng frame và media.
- Chặn truy cập dataset/imported model ngoài project.
- Validate source discriminator, provider parameters, capability và confidence.
- Upload artifact, validation status và từ chối model chưa `ready`.
- YOLO World prompt validation.
- Convert pixel/normalized `xywh` và `xyxy`.
- Validate, simplify và clamp polygon.
- Xử lý class đã map, chưa map và tạo class có chủ đích.
- Agent timeout, HTTP error và JSON không hợp lệ.
- Endpoint prediction không ghi annotation.

Frontend verification:

- Chuyển đúng giữa Import model và YOLO World mà không giữ config sai source.
- Upload model hiển thị đúng validation state.
- Output selector phản ánh capability của model/provider.
- Bbox xuất hiện, select/resize/delete được.
- Polygon xuất hiện và chỉnh vertex được.
- Một lần Undo xóa toàn bộ prediction batch.
- Save rồi reload giữ đúng shape và metadata.
- Chuyển frame trong lúc inference không chèn kết quả sai frame.
- Manual annotation không bị thay đổi.
- Lint, TypeScript build và kiểm thử end-to-end trên native route.

## 11. Thứ tự triển khai

1. Tạo `AutoLabelModel`, provider registry và API quản lý imported model.
2. Uploaded YOLO detection và frame inference API.
3. Draft/history/Undo/Save integration cho bounding box.
4. YOLO World bounding-box provider và prompt UI.
5. Uploaded YOLO segmentation và polygon output.
6. Segmentation refiner cho YOLO World nếu cần polygon từ open-vocabulary prompt.
7. Class mapping, AI badges và merge strategy.
8. Test, tài liệu và rollout backend/agent/frontend.

Bounding box nên hoàn thành trước để xác nhận toàn bộ request, draft và save
flow. Segmentation sau đó chỉ mở rộng contract và mapper, không xây một workflow
editor thứ hai.

## 12. Acceptance criteria

Tính năng hoàn thành khi:

1. `Run Model` vẫn chỉ dùng model được train từ project.
2. Auto Label mặc định hiển thị flow upload/chọn imported model tối giản; provider
   registry vẫn độc lập để mở rộng YOLO World và model khác.
3. Người dùng import, validate và chạy YOLO detection/segmentation model.
4. YOLO World nhận project label prompts và tạo bbox draft.
5. UI không cho chọn Polygon khi source không có capability tương ứng.
6. Detection model tạo rectangle draft đúng tọa độ.
7. Segmentation model tạo polygon draft chỉnh sửa được.
8. Prediction tham gia Undo/Redo và dirty-state của editor.
9. Người dùng có thể Save và reload mà không mất metadata.
10. Annotation thủ công luôn được giữ nguyên.
11. Request cũ không thể ghi kết quả vào frame mới.
12. Không có MinIO credential hoặc agent token xuất hiện trong browser.
