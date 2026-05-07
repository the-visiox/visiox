# VisioX Backend - Agent notes

This repo is the **Django** backend for the VisioX computer vision platform. It pairs with the **Next.js** frontend in the sibling repo `visiox-ui`.

## Quick reference

| Topic | Location |
|--------|-----------|
| Django settings | `visiox/settings.py` |
| API routing | `visiox/urls.py` |
| CVAT integration | `datasets/services/cvat.py` |
| Dataset browser and frame endpoints | `datasets/views/dataset_view.py` |
| Job annotations and review flow | `annotations/views/task_view.py`, `annotations/views/review_view.py` |
| Billing and API key auth | `billing/`, `billing/backends.py` |

## Runtime

- Main API dev server: `python manage.py runserver 0.0.0.0:8000`
- Background workers: Celery worker and beat are defined in `docker-compose.yml`
- Default persistence: PostgreSQL plus Redis
- Optional modes: CVAT-enabled mode and `VISIOX_STANDALONE`

## Testing rule

- After creating or changing functionality, the agent must run the most relevant verification before handing work back.
- For backend changes, prefer the narrowest useful command first, such as `python manage.py test <app_or_test_case>`, and expand only when needed.
- When the change affects routing, settings, migrations, or shared services, run broader verification if practical.
- Do not claim a feature is done without reporting which verification command was run and whether it passed.
- If a test cannot be run because of missing services, environment setup, or unrelated repo failures, the agent must say that clearly and explain the blocker.
