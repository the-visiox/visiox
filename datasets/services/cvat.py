import logging
import threading
from urllib.parse import urlparse

from django.conf import settings
from cvat_sdk.core.client import Client

logger = logging.getLogger(__name__)

CVAT_HOST = getattr(settings, 'CVAT_INTERNAL_HOST', 'http://localhost:8080')
CVAT_PUBLIC_URL = getattr(settings, 'CVAT_PUBLIC_URL', 'http://localhost:8080')
CVAT_USERNAME = getattr(settings, 'CVAT_USERNAME', 'admin')
CVAT_PASSWORD = getattr(settings, 'CVAT_PASSWORD', 'master123')
CVAT_WEBHOOK_URL = getattr(
    settings, 'CVAT_WEBHOOK_URL',
    'http://host.docker.internal:8000/api/datasets/cvat-webhook/',
)

_client_lock = threading.Lock()
_cached_client: Client | None = None


def get_cvat_client() -> Client:
    """Return a thread-safe, lazily-cached CVAT SDK client."""
    global _cached_client
    if _cached_client is not None:
        return _cached_client

    with _client_lock:
        if _cached_client is not None:
            return _cached_client

        parsed = urlparse(CVAT_PUBLIC_URL)
        host_header = parsed.netloc or 'localhost:8080'

        client = Client(CVAT_HOST, check_server_version=False)
        client.api_client.set_default_header('Host', host_header)
        client.api_client.set_default_header('Origin', CVAT_PUBLIC_URL)
        client.login((CVAT_USERNAME, CVAT_PASSWORD))
        _cached_client = client
        return client


def invalidate_client():
    """Force re-login on next call (e.g. after auth failure)."""
    global _cached_client
    with _client_lock:
        _cached_client = None


# ── Project / Task CRUD ──────────────────────────────────────────────────────

def create_cvat_project(name: str, labels: list[dict] | None = None) -> int:
    labels = labels or [{'name': 'object'}]
    client = get_cvat_client()
    project = client.projects.create({'name': name, 'labels': labels})
    logger.info('Created CVAT project %s (id=%d)', name, project.id)
    return project.id


def create_cvat_task(project_id: int, name: str) -> int:
    client = get_cvat_client()
    task = client.tasks.create({'name': name, 'project_id': project_id})
    logger.info('Created CVAT task "%s" in project %d (task_id=%d)', name, project_id, task.id)
    return task.id


def upload_cvat_data(task_id: int, file_paths: str | list[str]) -> None:
    """Upload one or more files to a CVAT task.

    CVAT only accepts data upload once per task. If the task already has data,
    this will fail. For multiple files, pass a list to upload them as a batch.
    """
    if isinstance(file_paths, str):
        file_paths = [file_paths]
    client = get_cvat_client()
    task = client.tasks.retrieve(task_id)
    task.upload_data(resources=file_paths, params={'image_quality': 80})
    logger.info('Uploaded %d file(s) to CVAT task %d', len(file_paths), task_id)


def delete_cvat_task(task_id: int) -> bool:
    try:
        client = get_cvat_client()
        task = client.tasks.retrieve(task_id)
        task.remove()
        logger.info('Deleted CVAT task %d', task_id)
        return True
    except Exception:
        logger.exception('Failed to delete CVAT task %d', task_id)
        return False


def update_cvat_task(task_id: int, *, name: str | None = None) -> None:
    if not name:
        return
    try:
        import requests
        session = _authed_session()
        session.patch(
            f'{CVAT_HOST}/api/tasks/{task_id}',
            json={'name': name},
        )
        logger.info('Updated CVAT task %d name → "%s"', task_id, name)
    except Exception:
        logger.exception('Failed to update CVAT task %d', task_id)


# ── Query helpers ────────────────────────────────────────────────────────────

def get_cvat_task_url(task_id: int) -> str:
    return f'{CVAT_PUBLIC_URL}/tasks/{task_id}'


def get_cvat_task_metadata(task_id: int) -> dict:
    client = get_cvat_client()
    task = client.tasks.retrieve(task_id)

    try:
        annotations = task.get_annotations()
        total_labels = len(annotations.shapes) + len(annotations.tracks) + len(annotations.tags)
    except Exception:
        logger.warning('Could not fetch annotations for CVAT task %d', task_id)
        total_labels = 0

    return {
        'id': task.id,
        'name': task.name,
        'status': task.status,
        'total_labels': total_labels,
        'updated_at': task.updated_date,
    }


def get_cvat_task_stats(task_id: int) -> dict:
    """Return comprehensive CVAT task statistics including jobs and annotation breakdown."""
    session = _authed_session()
    parsed = urlparse(CVAT_PUBLIC_URL)
    host_header = parsed.netloc or 'localhost:8080'
    session.headers.update({'Host': host_header, 'Origin': CVAT_PUBLIC_URL})

    task_res = session.get(f'{CVAT_HOST}/api/tasks/{task_id}')
    if task_res.status_code != 200:
        return {'exists': False}

    task_data = task_res.json()

    jobs_res = session.get(f'{CVAT_HOST}/api/jobs', params={'task_id': task_id, 'page_size': 100})
    jobs = []
    if jobs_res.status_code == 200:
        for j in jobs_res.json().get('results', []):
            jobs.append({
                'id': j['id'],
                'stage': j.get('stage', ''),
                'state': j.get('state', ''),
                'frame_count': j.get('frame_count', 0),
                'assignee': j.get('assignee', {}).get('username') if j.get('assignee') else None,
            })

    ann_res = session.get(f'{CVAT_HOST}/api/tasks/{task_id}/annotations')
    shapes, tags, tracks = 0, 0, 0
    if ann_res.status_code == 200:
        ann = ann_res.json()
        shapes = len(ann.get('shapes', []))
        tags = len(ann.get('tags', []))
        tracks = len(ann.get('tracks', []))

    return {
        'exists': True,
        'task_id': task_data['id'],
        'name': task_data.get('name', ''),
        'status': task_data.get('status', ''),
        'size': task_data.get('size', 0),
        'mode': task_data.get('mode', ''),
        'dimension': task_data.get('dimension', '2d'),
        'created_date': task_data.get('created_date'),
        'updated_date': task_data.get('updated_date'),
        'image_quality': task_data.get('image_quality', 0),
        'jobs': jobs,
        'annotations': {
            'shapes': shapes,
            'tags': tags,
            'tracks': tracks,
            'total': shapes + tags + tracks,
        },
        'url': f'{CVAT_PUBLIC_URL}/tasks/{task_id}',
    }


# ── Data browser helpers ─────────────────────────────────────────────────────

def get_cvat_browser_data(task_id: int, project_id: int | None = None) -> dict:
    """Return frame list, labels, and annotations for the data browser UI."""
    session = _authed_session()
    parsed = urlparse(CVAT_PUBLIC_URL)
    host_header = parsed.netloc or 'localhost:8080'
    session.headers.update({'Host': host_header, 'Origin': CVAT_PUBLIC_URL})

    # Frame metadata
    meta_res = session.get(f'{CVAT_HOST}/api/tasks/{task_id}/data/meta')
    frames_raw = meta_res.json().get('frames', []) if meta_res.ok else []

    # Labels (from project or task)
    labels_map = {}
    label_endpoint = f'{CVAT_HOST}/api/labels'
    params = {'project_id': project_id} if project_id else {'task_id': task_id}
    lab_res = session.get(label_endpoint, params={**params, 'page_size': 200})
    if lab_res.ok:
        for l in lab_res.json().get('results', []):
            labels_map[l['id']] = {
                'id': l['id'],
                'name': l['name'],
                'color': l.get('color', '#40e020'),
                'type': l.get('type', 'any'),
            }

    # Annotations
    ann_res = session.get(f'{CVAT_HOST}/api/tasks/{task_id}/annotations')
    raw_ann = ann_res.json() if ann_res.ok else {}

    shapes_by_frame: dict[int, list] = {}
    for shape in raw_ann.get('shapes', []):
        frame_num = shape.get('frame', 0)
        label_id = shape.get('label_id')
        label_info = labels_map.get(label_id, {})
        shapes_by_frame.setdefault(frame_num, []).append({
            'id': shape.get('id'),
            'type': shape.get('type', 'rectangle'),
            'label_id': label_id,
            'label': label_info.get('name', 'unknown'),
            'color': label_info.get('color', '#40e020'),
            'points': shape.get('points', []),
            'occluded': shape.get('occluded', False),
            'attributes': shape.get('attributes', []),
        })

    frames = []
    for i, f in enumerate(frames_raw):
        frames.append({
            'frame': i,
            'name': f.get('name', f'frame_{i}'),
            'width': f.get('width', 0),
            'height': f.get('height', 0),
            'annotations': shapes_by_frame.get(i, []),
        })

    return {
        'task_id': task_id,
        'frame_count': len(frames),
        'labels': list(labels_map.values()),
        'frames': frames,
        'annotation_count': sum(len(v) for v in shapes_by_frame.values()),
    }


def get_cvat_frame_image(task_id: int, frame_num: int, quality: str = 'compressed') -> tuple[bytes, str]:
    """Proxy a single frame image from CVAT. Returns (image_bytes, content_type)."""
    session = _authed_session()
    parsed = urlparse(CVAT_PUBLIC_URL)
    session.headers.update({
        'Host': parsed.netloc or 'localhost:8080',
        'Origin': CVAT_PUBLIC_URL,
    })
    res = session.get(
        f'{CVAT_HOST}/api/tasks/{task_id}/data',
        params={'type': 'frame', 'number': frame_num, 'quality': quality},
        stream=True,
    )
    if not res.ok:
        raise ValueError(f'CVAT returned {res.status_code} for frame {frame_num}')
    content_type = res.headers.get('content-type', 'image/jpeg')
    return res.content, content_type


# ── Provisioning helper (used by views) ─────────────────────────────────────

def cvat_task_exists(task_id: int) -> bool:
    """Check whether a CVAT task still exists (fast HEAD-style check)."""
    try:
        session = _authed_session()
        session.headers.update({'Host': 'localhost:8080', 'Origin': 'http://localhost:8080'})
        res = session.get(f'{CVAT_HOST}/api/tasks/{task_id}')
        return res.status_code == 200
    except Exception:
        return False


def repair_orphaned_datasets() -> list[dict]:
    """Find VisioX datasets whose CVAT task no longer exists and recreate them."""
    from datasets.models import Dataset

    repaired = []
    for ds in Dataset.objects.filter(cvat_task_id__isnull=False).select_related('project'):
        if cvat_task_exists(ds.cvat_task_id):
            continue

        logger.warning('Orphaned dataset %d (%s): CVAT task %d missing', ds.id, ds.name, ds.cvat_task_id)
        project = ds.project
        if not project.cvat_project_id:
            continue

        try:
            new_task_id = create_cvat_task(project.cvat_project_id, ds.name)

            media_paths = list(
                ds.media_files.filter(type='image').values_list('file', flat=True)
            )
            if media_paths:
                from django.conf import settings as dj_settings
                import os
                full_paths = [os.path.join(str(dj_settings.MEDIA_ROOT), p) for p in media_paths]
                upload_cvat_data(new_task_id, full_paths)

            old_id = ds.cvat_task_id
            ds.cvat_task_id = new_task_id
            ds.save(update_fields=['cvat_task_id'])

            repaired.append({'dataset': ds.id, 'name': ds.name, 'old_task': old_id, 'new_task': new_task_id})
            logger.info('Repaired dataset %d: task %d -> %d', ds.id, old_id, new_task_id)
        except Exception:
            logger.exception('Failed to repair dataset %d', ds.id)

    return repaired


def ensure_cvat_task(dataset) -> int | None:
    """Ensure the dataset has a linked CVAT task.

    Creates the CVAT project (if needed) and task, saves both models,
    and returns the task_id. No-op when ``VISIOX_STANDALONE`` is enabled.
    """
    if getattr(settings, 'VISIOX_STANDALONE', False):
        return None
    if dataset.cvat_task_id:
        if cvat_task_exists(dataset.cvat_task_id):
            return dataset.cvat_task_id
        logger.warning('CVAT task %d for dataset %d no longer exists, recreating', dataset.cvat_task_id, dataset.id)

    project = dataset.project
    cvat_project_id = project.cvat_project_id

    if not cvat_project_id:
        cvat_project_id = create_cvat_project(project.name)
        project.cvat_project_id = cvat_project_id
        project.save(update_fields=['cvat_project_id'])
        register_cvat_webhook(cvat_project_id)

    task_id = create_cvat_task(cvat_project_id, dataset.name)
    dataset.cvat_task_id = task_id
    dataset.save(update_fields=['cvat_task_id'])
    return task_id


# ── Webhook registration ────────────────────────────────────────────────────

def _authed_session():
    import requests
    session = requests.Session()
    session.auth = (CVAT_USERNAME, CVAT_PASSWORD)
    return session


def register_cvat_webhook(cvat_project_id: int) -> int | None:
    """Register a webhook for a CVAT project pointing to VisioX."""
    session = _authed_session()

    res = session.get(f'{CVAT_HOST}/api/webhooks')
    if res.status_code == 200:
        for wh in res.json().get('results', []):
            if wh['target_url'] == CVAT_WEBHOOK_URL and wh.get('project_id') == cvat_project_id:
                logger.debug('Webhook already exists for CVAT project %d', cvat_project_id)
                return wh['id']

    webhook_spec = {
        'target_url': CVAT_WEBHOOK_URL,
        'description': 'VisioX Automated Sync',
        'content_type': 'application/json',
        'is_active': True,
        'type': 'project',
        'project_id': cvat_project_id,
        'events': ['create:task', 'update:task', 'update:job', 'delete:task'],
    }

    res = session.post(f'{CVAT_HOST}/api/webhooks', json=webhook_spec)
    if res.status_code in (200, 201):
        wh_id = res.json()['id']
        logger.info('Registered webhook %d for CVAT project %d', wh_id, cvat_project_id)
        return wh_id

    logger.error('Failed to register webhook for CVAT project %d: %s', cvat_project_id, res.text)
    return None
