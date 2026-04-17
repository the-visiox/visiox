## VisioX Backend

Django + Django REST Framework API for the VisioX computer vision platform: teams, projects, datasets, media upload, **annotations**, labeling jobs, training, deployments, billing, and OpenAPI docs.

## Requirements

- Python 3.12+ (recommended)
- PostgreSQL 16+
- Redis 7+ (Celery broker / cache)
- `pip` and a virtual environment

## Chạy tách riêng: DB / Backend / Frontend

Mở **3 terminal** độc lập để dễ debug:

1. Terminal A: chạy **Database + Redis**
2. Terminal B: chạy **Django Backend**
3. Terminal C: chạy **Next.js Frontend** (`visiox-ui`)

---

### Terminal A — Database (Postgres) + Redis

> Trong repo `visiox`

```bash
docker compose up -d db redis
```

Kiểm tra nhanh:

```bash
docker compose ps
```

Kỳ vọng `db` và `redis` ở trạng thái `Up`.

---

### Terminal B — Backend (Django)

> Trong repo `visiox`

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
cp env.example .env
```

Chỉnh `.env` (khi DB chạy bằng Docker ở terminal A):

```env
DATABASE_HOST=localhost
DATABASE_PORT=5433
DATABASE_NAME=visiox_db
DATABASE_USER=postgres
DATABASE_PASSWORD=postgres
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0
```

Chạy migrate + seed:

```bash
python manage.py migrate
python manage.py setup_groups
python manage.py seed_demo_data
```

Nếu bạn dùng Conda/env riêng (ví dụ `py312`), ưu tiên chạy bằng đúng Python executable để tránh nhầm môi trường:

```bash
C:\Users\Admin\miniconda3\envs\py312\python.exe manage.py migrate
```

> Quan trọng cho annotation: migration `datasets.0006_medialabelprofile` phải ở trạng thái **[X]**. Nếu thiếu, thao tác save label profile sẽ lỗi `relation "media_label_profiles" does not exist` (frontend có thể hiện `Annotations saved, but label profile sync failed.`).

Kiểm tra nhanh:

```bash
python manage.py showmigrations datasets
```

Chạy API:

```bash
python manage.py runserver 0.0.0.0:8000
```

Test nhanh:
- Swagger: `http://localhost:8000/api/docs/`
- Health check thủ công: mở `http://localhost:8000/api/schema/`

---

### Terminal C — Frontend (Next.js)

> Trong repo `visiox-ui`

```bash
pnpm install
cp .env.local.example .env.local
```

Đảm bảo `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Chạy frontend:

```bash
pnpm dev
```

Mở `http://localhost:3000`, đăng nhập:
- Email: `demo@visiox.ai`
- Password: `Demo1234!`

## Database host: Docker vs local CLI

- **`DATABASE_HOST=db`** resolves only **inside** Docker Compose (service name). Running `python manage.py` **on your PC** (Windows/macOS/Linux) must use **`localhost`** (or `127.0.0.1`).
- Compose maps Postgres to host port **`5433`** by default (`DB_HOST_PORT`, see `docker-compose.yml`). From the host, use `DATABASE_PORT=5433` when talking to the containerized DB. Use **`5432`** if PostgreSQL is installed natively on the machine.

Example **host** `.env` when DB runs in Docker:

```env
DATABASE_NAME=visiox_db
DATABASE_USER=postgres
DATABASE_PASSWORD=postgres
DATABASE_HOST=localhost
DATABASE_PORT=5433

CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0
```

Inside containers, Compose overrides `DATABASE_HOST` to `db` where needed.

## 1) Local setup (without Docker)

```bash
cd visiox
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix: source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env
# Edit .env: localhost + correct DATABASE_PORT (5432 or 5433)
python manage.py migrate
python manage.py setup_groups
python manage.py seed_demo_data
python manage.py runserver 0.0.0.0:8000
```

## 2) Docker setup

```bash
docker compose up --build -d db redis
docker compose exec api python manage.py migrate
docker compose exec api python manage.py setup_groups
docker compose exec api python manage.py seed_demo_data
```

Or bring up the full stack (`api`, `worker`, `beat`) per `docker-compose.yml`.

## API surface (selected)

| Area | Base path |
|------|-----------|
| Auth (JWT) | `/api/auth/` — `login`, `register`, `token/refresh`, `logout` |
| Teams / projects / datasets | `/api/teams/`, `/api/projects/`, `/api/datasets/` |
| Classes (labels) | `/api/classes/?project=<id>` |
| Annotations (CRUD, bulk) | `/api/annotations/` |
| **Jobs** (alias for labeling tasks) | `/api/jobs/` — same viewset as `/api/tasks/` |
| **Job annotations** | `GET` / `PATCH /api/jobs/{id}/annotations/` (PATCH replaces all annotations for that job’s media) |
| **Job issues (QA comments)** | `GET` / `POST /api/jobs/{id}/issues/` — POST body: `{"body": "..."}` |
| Training / deploy / billing | `/api/architectures/`, `/api/training-jobs/`, `/api/registry/`, `/api/endpoints/`, billing routes |

## Documentation URLs

- Swagger: `http://localhost:8000/api/docs/`
- ReDoc: `http://localhost:8000/api/redoc/`
- OpenAPI schema: `http://localhost:8000/api/schema/`
- Admin: `http://localhost:8000/admin/`
- Silk (when `DEBUG=True`): `http://localhost:8000/silk/`

## Demo account

After `seed_demo_data`:

- **Email:** `demo@visiox.ai`
- **Password:** `Demo1234!`

## CORS

Default allowed origins include `http://localhost:3000` and `http://127.0.0.1:3000`. For other front-end origins, set **`CORS_ALLOWED_ORIGINS`** (comma-separated) in `.env`.

## Useful commands

```bash
python manage.py runserver 0.0.0.0:8000
celery -A visiox worker -l info
celery -A visiox beat -l info
python manage.py makemigrations
python manage.py migrate
python manage.py showmigrations datasets
```

## Frontend pairing

The **visiox-ui** Next app uses `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`) and JWT from `/api/auth/login/`.
