# VisioX Backend — Agent Configuration

Django REST API backend for the VisioX computer vision platform: teams, projects, datasets, media, annotations, training, deployments, and billing.

Pairs with **visiox-ui** (Next.js frontend) in the sibling repo.

## Quick Reference

| Topic | Location |
|--------|-----------|
| Django settings | `visiox/settings.py` |
| API routing | `visiox/urls.py` |
| CVAT integration | `datasets/services/cvat.py` |
| Dataset browser / frame endpoints | `datasets/views/dataset_view.py` |
| Job annotations and review | `annotations/views/task_view.py`, `annotations/views/review_view.py` |
| Billing and API key auth | `billing/`, `billing/backends.py` |
| Architecture diagrams | `docs/ARCHITECTURE_DIAGRAMS.md` |
| Product roadmap | `docs/ROADMAP.md` |

## Architecture

```
visiox-ui/          ← Next.js frontend
  ↕ REST API (JWT)
visiox/             ← This repo — Django API, Celery, PostgreSQL, Redis
  ↕ cvat-sdk + REST
cvat/               ← Customized CVAT fork (annotation engine, optional)
```

## Runtime

- Dev server: `python manage.py runserver 0.0.0.0:8000`
- Background workers: `celery -A visiox worker -l info` and `celery -A visiox beat -l info`
- Full stack: `docker compose up` (see `docker-compose.yml`)
- Default persistence: PostgreSQL + Redis
- Modes: CVAT-enabled (default) or `VISIOX_STANDALONE=true`

## Domain Apps

| App | Responsibility |
|-----|----------------|
| `core` | Custom user model, permissions, JWT query auth |
| `authentication` | Login, register, token refresh, OAuth |
| `teams` | Teams, members, roles |
| `projects` | Project metadata, CVAT project mapping |
| `datasets` | Dataset records, media upload, frame proxy, CVAT task mapping |
| `annotations` | Classes, annotations, jobs, reviews, quality, export |
| `training` | Architectures, training jobs, experiments |
| `deployments` | Model registry, endpoints, monitoring |
| `billing` | Plans, subscriptions, API keys, Stripe webhooks |
| `dataverse` | Public dataset hub and forking |

## Key Integration Points

- **CVAT**: Optional. Enabled when `CVAT_HOST` is set. Integration concentrated in `datasets/services/cvat.py`.
- **Celery**: Async tasks for training, media processing, and scheduled syncs.
- **Stripe**: Billing webhooks at `/api/webhooks/stripe/`.
- **JWT**: `djangorestframework-simplejwt`; some image endpoints accept `?token=<jwt>` query param.

## Testing Rule

- After creating or changing functionality, run the most relevant verification before finishing.
- For backend changes: `python manage.py test <app_or_test_case>` (narrow first, expand when needed).
- When the change affects routing, settings, migrations, or shared services, run broader verification.
- Do not claim a feature is done without reporting which verification command was run and whether it passed.
- If a test cannot run due to missing services or environment, state that clearly with the blocker.

## Useful Commands

```bash
python manage.py runserver 0.0.0.0:8000
python manage.py migrate
python manage.py showmigrations datasets
python manage.py setup_groups
python manage.py seed_demo_data
celery -A visiox worker -l info
celery -A visiox beat -l info
```

## Demo Account

After `seed_demo_data`:
- **Email:** `demo@visiox.ai`
- **Password:** `Demo1234!`
