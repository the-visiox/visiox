# Triển khai Dataset Worker cùng máy MinIO

Tài liệu này hướng dẫn chạy Celery worker dành riêng cho queue `datasets` trên máy
`10.29.30.20`, nơi đang chạy PostgreSQL, Redis và MinIO. Django API và frontend
tiếp tục chạy trên máy `10.29.30.9`.

Hạ tầng `.20` đang thuộc Compose project `infiniq`. Tất cả lệnh trong tài liệu
này dùng `-p infiniq`; thiếu tham số này có thể báo
`service "worker-datasets" is not running` dù container vẫn hoạt động.

Celery hostname chứa container ID và thay đổi sau khi recreate. Không hardcode
hostname trong script; dùng `inspect` không có `--destination`.

## 1. Kiến trúc mục tiêu

```text
10.29.30.9
├── Next.js UI :3000
├── Django API :8000
├── Celery general worker → queue celery
└── Celery beat

10.29.30.20
├── PostgreSQL :5432
├── Redis :6379
├── MinIO API :9000
├── MinIO Console :9001
└── Celery dataset worker → queue datasets
```

Dataset worker trên `.20` dùng DNS nội bộ Docker:

```text
PostgreSQL: db:5432
Redis:      redis:6379
MinIO:      minio:9000
```

Frontend vẫn gọi Django API tại `http://10.29.30.9:8000`. Không chạy thêm API
hoặc expose port `8000` trên máy `.20`.

## 2. Điều kiện trước khi triển khai

- Máy `.20` đã cài Docker Engine, Docker Compose plugin và Git.
- PostgreSQL, Redis và MinIO hiện đang healthy.
- Backend `.9` và dataset worker `.20` sử dụng cùng source commit.
- Migration `datasets.0014_datasetimportjob` đã được áp dụng.
- Bucket `visiox-media` đã tồn tại.
- Có MinIO service account dành cho VisioX. Không dùng root account lâu dài.
- Không restart worker `.9` khi import job đang chạy.

Các placeholder trong tài liệu phải được thay bằng giá trị thật:

```text
<DEPLOY_USER>
<DEPLOY_BRANCH>
<DJANGO_SECRET_KEY>
<DATABASE_PASSWORD>
<MINIO_ACCESS_KEY>
<MINIO_SECRET_KEY>
```

Không giữ dấu `<` và `>` sau khi thay giá trị.

## 3. Chuẩn bị source trên máy `.9`

Source chưa commit sẽ không thể nhận được bằng `git pull` trên `.20`. Kiểm tra
và commit toàn bộ thay đổi cần triển khai trước:

```powershell
cd C:\Users\Admin\project\visiox

git status
git diff --stat
git switch -c <DEPLOY_BRANCH>
git add -A
git diff --cached --stat
git commit -m "Deploy dataset worker near MinIO"
git push -u origin <DEPLOY_BRANCH>
```

Không commit `.env`, credentials hoặc token.

## 4. Clone source trên máy `.20`

Kết nối tới máy `.20`:

```bash
ssh <DEPLOY_USER>@10.29.30.20
```

Chuẩn bị thư mục:

```bash
sudo mkdir -p ~/project/visiox
sudo chown "$USER":"$USER" ~/project/visiox
```

Clone source:

```bash
git clone --branch <DEPLOY_BRANCH> \
  git@github.com:the-visiox/visiox.git \
  ~/project/visiox
```

Nếu source đã tồn tại:

```bash
cd ~/project/visiox
git fetch origin
git switch <DEPLOY_BRANCH>
git pull --ff-only origin <DEPLOY_BRANCH>
```

Xác nhận commit đang chạy:

```bash
git branch --show-current
git rev-parse HEAD
git status --short
```

Working tree trên server nên sạch trước khi build image.

## 5. Ngăn credentials bị đóng gói vào Docker image

Tạo `~/project/visiox/.dockerignore` nếu chưa có:

```text
.git
.gitignore
.env
.env.*
!env.example

venv
.venv
__pycache__
*.pyc
*.pyo

media
.next
node_modules
```

`Dockerfile.worker` có `COPY . .`; vì vậy bước này bắt buộc để `.env.worker` không
bị ghi vào image layer.

## 6. Tạo environment riêng cho dataset worker

Tạo `~/project/visiox/.env.worker` từ file mẫu:

```bash
cd ~/project/visiox
cp env.worker.example .env.worker
nano .env.worker
```

Nội dung mẫu:

```env
SECRET_KEY=<DJANGO_SECRET_KEY>

DATABASE_NAME=visiox_db
DATABASE_USER=postgres
DATABASE_PASSWORD=<DATABASE_PASSWORD>
DATABASE_HOST=db
DATABASE_PORT=5432
DATABASE_CONNECT_TIMEOUT=5

USE_CELERY=True
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

USE_MINIO=True
MINIO_ENDPOINT=http://minio:9000
MINIO_ACCESS_KEY=<MINIO_ACCESS_KEY>
MINIO_SECRET_KEY=<MINIO_SECRET_KEY>
MINIO_BUCKET=visiox-media

DATASET_IMPORT_STORAGE_WORKERS=6
DATASET_IMPORT_BATCH_SIZE=24
```

Video frame extraction runs inside `worker-datasets` using OpenCV and NumPy.
It compares color, layout, and edge descriptors and does not require a model,
GPU, or separate ML checkpoint. The default minimum visual difference is 15%;
frames below that threshold are treated as near-duplicates.

Large browser uploads bypass the Django API and use presigned MinIO `PUT` URLs.
Configure bucket CORS to allow `PUT` and the `Content-Type` header from the
frontend origins, and ensure the `MINIO_ENDPOINT` configured on the API host is
reachable from user browsers (do not presign an internal Docker-only hostname).
Set `DATASET_DIRECT_UPLOAD_EXPIRES=3600` on the API host; frame extraction starts
on `worker-datasets` only after the browser commits every uploaded object.

Bảo vệ file:

```bash
chmod 600 ~/project/visiox/.env.worker
```

`SECRET_KEY` nên giống backend `.9`. Database và MinIO credentials phải khớp
với infrastructure đang chạy.

## 7. Thêm worker vào `docker-compose.infra.yml`

Thêm service sau dưới `services:`:

```yaml
  worker-datasets:
    build:
      context: .
      dockerfile: Dockerfile.worker
    restart: unless-stopped
    command: >
      celery -A visiox worker
      -l info
      -Q datasets
      --concurrency=1
      --prefetch-multiplier=1
      --hostname=dataset-worker@%h
    env_file:
      - .env.worker
    environment:
      DATABASE_HOST: db
      DATABASE_PORT: "5432"
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/0
      MINIO_ENDPOINT: http://minio:9000
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
      minio:
        condition: service_healthy
```

Worker không cần `ports`. Tất cả kết nối đều do worker chủ động mở tới service
nội bộ.

Có thể xóa dòng `version: '3.9'`; Docker Compose mới không còn sử dụng thuộc tính
này.

## 8. Kiểm tra cấu hình trước khi chạy

```bash
cd ~/project/visiox

docker compose -p infiniq -f docker-compose.infra.yml config --quiet
docker compose -p infiniq -f docker-compose.infra.yml config | grep '<'
```

Lệnh `grep '<'` không được trả về placeholder nào.

Không chia sẻ output đầy đủ của `docker compose config`, vì output có thể chứa
database password, MinIO secret và Django secret.

Kiểm tra infrastructure:

```bash
docker compose -p infiniq -f docker-compose.infra.yml ps
```

`db`, `redis` và `minio` phải ở trạng thái `healthy`.

## 9. Build image và kiểm tra migration

Build riêng worker:

```bash
docker compose -p infiniq -f docker-compose.infra.yml build worker-datasets
```

Kiểm tra migration:

```bash
docker compose -p infiniq -f docker-compose.infra.yml run --rm \
  worker-datasets python manage.py showmigrations datasets
```

Kết quả phải chứa:

```text
[X] 0014_datasetimportjob
```

Nếu migration chưa áp dụng, ưu tiên chạy từ API `.9` đang sử dụng cùng commit:

```bash
docker compose exec api python manage.py migrate --noinput
```

Hoặc chạy one-off trên `.20`:

```bash
docker compose -p infiniq -f docker-compose.infra.yml run --rm \
  worker-datasets python manage.py migrate --noinput
```

Chỉ cần chạy migration từ một nơi.

## 10. Khởi động dataset worker

```bash
docker compose -p infiniq -f docker-compose.infra.yml up -d \
  --no-deps --force-recreate worker-datasets
docker compose -p infiniq -f docker-compose.infra.yml ps
docker compose -p infiniq -f docker-compose.infra.yml logs -f worker-datasets
```

Log mong đợi:

```text
Connected to redis://redis:6379/0
dataset-worker@... ready.
```

Xác nhận worker không chạy bằng root:

```bash
docker compose -p infiniq -f docker-compose.infra.yml exec -T worker-datasets id
```

Kết quả phải có `uid=10001(visiox)` và không phải `uid=0(root)`.

Danh sách queue phải có `datasets`.

Có thể kiểm tra từ container:

```bash
docker compose -p infiniq -f docker-compose.infra.yml exec -T worker-datasets \
  celery -A visiox inspect active_queues
```

## 11. Chuyển queue trên máy `.9`

Chờ import đang chạy hoàn thành. Sau đó sửa worker trên máy `.9` từ:

```yaml
command: celery -A visiox worker -l info -Q celery,datasets
```

thành:

```yaml
command: >
  celery -A visiox worker
  -l info
  -Q celery
  --concurrency=2
  --prefetch-multiplier=1
  --hostname=general-worker@%h
```

Recreate worker `.9`:

```bash
docker compose up -d --no-deps --force-recreate worker
docker compose logs -f worker
```

Nếu worker `.9` vẫn nghe queue `datasets`, Redis có thể giao import job cho `.9`
thay vì worker gần MinIO trên `.20`.

## 12. Kiểm thử end-to-end

1. Mở một dataset trên UI.
2. Upload một ZIP YOLO nhỏ hoặc một nhóm ảnh thử nghiệm.
3. Kiểm tra UI chuyển `queued` → `running` → `done`.
4. Trên `.20`, kiểm tra task xuất hiện trong log:

```bash
docker compose -p infiniq -f docker-compose.infra.yml logs -f worker-datasets
```

5. Kiểm tra MinIO có object trong `visiox-media`.
6. Sau khi job hoàn tất, prefix `import-staging/.../jobs/{job_id}` phải được dọn.
7. Xác nhận ảnh hiển thị và annotation YOLO được import đúng.

## 13. Cập nhật source về sau

Trên `.20`:

```bash
cd ~/project/visiox
git fetch origin
git pull --ff-only origin <DEPLOY_BRANCH>

docker compose -p infiniq -f docker-compose.infra.yml build worker-datasets
docker compose -p infiniq -f docker-compose.infra.yml \
  up -d --no-deps --force-recreate worker-datasets
```

Luôn chạy migration trước khi worker mới nhận task nếu commit có migration mới.

Nên ghi lại commit đang triển khai:

```bash
git rev-parse HEAD
```

## 14. Điều chỉnh hiệu năng

Cấu hình ban đầu:

```env
DATASET_IMPORT_STORAGE_WORKERS=6
DATASET_IMPORT_BATCH_SIZE=24
```

Celery worker dùng:

```text
--concurrency=1
```

Mỗi import job đã có tối đa 6 thread I/O MinIO. Không tăng Celery concurrency
trước khi kiểm tra CPU, RAM, network throughput và disk latency trên `.20`.

Nếu MinIO hoặc disk bị tải cao, giảm storage workers xuống `4`. Nếu máy còn nhiều
tài nguyên và network/disk chưa bão hòa, có thể thử `8`, nhưng không vượt quá giới
hạn `16` trong backend.

Sau khi thay `.env.worker`, recreate worker:

```bash
docker compose -p infiniq -f docker-compose.infra.yml \
  up -d --no-deps --force-recreate worker-datasets
```

## 15. Rollback

Để ngừng nhận dataset job trên `.20`:

```bash
docker compose -p infiniq -f docker-compose.infra.yml stop worker-datasets
```

Sau đó cho worker `.9` nghe lại cả hai queue:

```yaml
command: celery -A visiox worker -l info -Q celery,datasets
```

```bash
docker compose up -d --no-deps --force-recreate worker
```

Không stop worker khi task đang active. Kiểm tra trước:

```bash
docker compose -p infiniq -f docker-compose.infra.yml exec -T worker-datasets \
  celery -A visiox inspect active
```

## 16. Checklist triển khai

- [ ] Source trên `.9` đã commit và push.
- [ ] Source trên `.20` đúng branch và commit.
- [ ] `.dockerignore` loại trừ `.env*`.
- [ ] Worker chạy bằng user `visiox` với UID `10001`, không phải root.
- [ ] `.env.worker` không còn placeholder và có permission `600`.
- [ ] PostgreSQL, Redis và MinIO healthy.
- [ ] Migration `0014_datasetimportjob` đã áp dụng.
- [ ] `worker-datasets` kết nối Redis và ở trạng thái ready.
- [ ] Worker `.20` chỉ nghe queue `datasets`.
- [ ] Worker `.9` chỉ nghe queue `celery`.
- [ ] Upload thử nghiệm hoàn thành và staging được dọn.
- [ ] Credentials đã được rotate nếu từng xuất hiện trong log/chat.
