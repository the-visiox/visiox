## VisioX Backend

Backend API for the VisioX computer vision platform, built with Django + Django REST Framework.

## Requirements

- Python 3.12+ (recommended)
- PostgreSQL 16+
- Redis 7+ (for Celery)
- `pip` and virtual environment support

## 1) Local Setup (without Docker)

1. Clone repo and move to project folder:

```bash
git clone <your-repo-url>
cd visiox
```

2. Create and activate virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Create environment file:

```bash
cp env.example .env
```

5. Update `.env` values for your local PostgreSQL/Redis setup.

Example minimal config:

```env
DATABASE_NAME=visiox_db
DATABASE_USER=postgres
DATABASE_PASSWORD=postgres
DATABASE_HOST=localhost
DATABASE_PORT=5432

CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

6. Run migrations:

```bash
python manage.py migrate
```

7. Create role groups and seed demo data (optional but recommended):

```bash
python manage.py setup_groups
python manage.py seed_demo_data
```

8. Start API server:

```bash
python manage.py runserver 0.0.0.0:8000
```

## 2) Docker Setup (recommended)

1. Create `.env` from example:

```bash
cp env.example .env
```

2. Start services:

```bash
docker compose up --build
```

This starts:
- `db` (PostgreSQL)
- `redis`
- `api` (Django at port `8000`)
- `worker` (Celery worker)
- `beat` (Celery beat)

3. Run migrations and seed (from another terminal):

```bash
docker compose exec api python manage.py migrate
docker compose exec api python manage.py setup_groups
docker compose exec api python manage.py seed_demo_data
```

## API Endpoints

- API base: `http://localhost:8000/api/`
- Swagger docs: `http://localhost:8000/api/docs/`
- ReDoc: `http://localhost:8000/api/redoc/`
- OpenAPI schema: `http://localhost:8000/api/schema/`
- Django admin: `http://localhost:8000/admin/`
- Silk profiler: `http://localhost:8000/silk/` (when `DEBUG=True`)

## Demo Account

When running `seed_demo_data`, a demo user is created:

- Email: `demo@visiox.ai`
- Password: `Demo1234!`

## Useful Commands

```bash
# Run development server
python manage.py runserver

# Run Celery worker
celery -A visiox worker -l info

# Run Celery beat
celery -A visiox beat -l info

# Create new migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate
```
