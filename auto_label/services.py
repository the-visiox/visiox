import hashlib
import logging
import math
import os
import tempfile
import threading
import time
from pathlib import Path

import requests
from django.conf import settings


logger = logging.getLogger(__name__)
_LOCAL_MODEL_CACHE = {}
_LOCAL_MODEL_LOCK = threading.Lock()


class AutoLabelInferenceError(RuntimeError):
    pass


def inference_confidence(value):
    if value in (None, ''):
        return 0.45
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('confidence must be a number between 0 and 1.') from exc
    if not 0 <= confidence <= 1:
        raise ValueError('confidence must be between 0 and 1.')
    return confidence


def _local_fallback_enabled():
    return bool(getattr(settings, 'AUTO_LABEL_LOCAL_FALLBACK', False))


def _local_model_path(model_spec):
    from core.storage import get_artifacts_storage

    storage_key = str(model_spec.get('storage_key') or '')
    if not storage_key or Path(storage_key).suffix.lower() != '.pt':
        raise AutoLabelInferenceError('Local fallback requires an Ultralytics .pt artifact.')
    signature = str(
        model_spec.get('checksum')
        or model_spec.get('sha256')
        or hashlib.sha256(storage_key.encode()).hexdigest()
    )
    cache_dir = Path(tempfile.gettempdir()) / 'visiox-auto-label-models'
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_dir / f'{signature}.pt'
    if destination.is_file() and destination.stat().st_size > 0:
        return destination

    storage = get_artifacts_storage()
    temporary = destination.with_suffix(f'.{os.getpid()}.{threading.get_ident()}.tmp')
    try:
        with storage.open(storage_key, 'rb') as source, temporary.open('wb') as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _local_model(model_spec):
    cache_key = str(
        model_spec.get('checksum')
        or model_spec.get('sha256')
        or model_spec.get('storage_key')
        or ''
    )
    with _LOCAL_MODEL_LOCK:
        cached = _LOCAL_MODEL_CACHE.get(cache_key)
        if cached is not None:
            return cached
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise AutoLabelInferenceError(
                'Local Auto Label fallback requires the ultralytics package.'
            ) from exc
        model = YOLO(str(_local_model_path(model_spec)))
        _LOCAL_MODEL_CACHE[cache_key] = model
        return model


def purge_temporary_model(model):
    if not getattr(model, 'is_temporary', False):
        return
    storage_key = model.model_file.name if model.model_file else ''
    cache_keys = {key for key in (model.checksum, storage_key) if key}
    with _LOCAL_MODEL_LOCK:
        for key in cache_keys:
            _LOCAL_MODEL_CACHE.pop(key, None)
    cache_dir = Path(tempfile.gettempdir()) / 'visiox-auto-label-models'
    signatures = {model.checksum} if model.checksum else set()
    if storage_key:
        signatures.add(hashlib.sha256(storage_key.encode()).hexdigest())
    for signature in signatures:
        (cache_dir / f'{signature}.pt').unlink(missing_ok=True)
    if storage_key:
        model.model_file.storage.delete(storage_key)
    model.model_file.name = ''
    model.status = 'failed'
    model.validation_error = 'Temporary model artifact removed after Auto Label.'
    model.save(update_fields=['model_file', 'status', 'validation_error', 'updated_at'])


def _local_predictions(payload):
    import cv2
    import numpy as np

    from datasets.models import Media

    model_spec = payload.get('model') or {}
    dataset_spec = payload.get('dataset') or {}
    dataset_id = dataset_spec.get('id')
    media_ids = [int(media_id) for media_id in dataset_spec.get('media_ids') or []]
    if not dataset_id or not media_ids:
        raise AutoLabelInferenceError('Local fallback requires a dataset and at least one media id.')
    if payload.get('output_type', 'bbox') != 'bbox':
        raise AutoLabelInferenceError('The local detection fallback supports bounding boxes only.')

    media_by_id = {
        media.id: media
        for media in Media.objects.filter(dataset_id=dataset_id, id__in=media_ids, type='image')
    }
    ordered_media = []
    images = []
    for media_id in media_ids:
        media = media_by_id.get(media_id)
        if media is None or not media.file:
            continue
        with media.file.open('rb') as source:
            image = cv2.imdecode(np.frombuffer(source.read(), dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            continue
        ordered_media.append(media)
        images.append(image)

    if not images:
        raise AutoLabelInferenceError('Local fallback could not read any requested dataset images.')

    started_at = time.perf_counter()
    predict_options = {
        'conf': inference_confidence(payload.get('confidence')),
        'verbose': False,
    }
    device = str(getattr(settings, 'AUTO_LABEL_LOCAL_DEVICE', '') or '').strip()
    if device:
        predict_options['device'] = device
    results = _local_model(model_spec).predict(images, **predict_options)

    predictions = []
    predicted_images = 0
    for media, result in zip(ordered_media, results):
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            continue
        predicted_images += 1
        names = result.names or {}
        for xyxy, confidence, class_index in zip(
            boxes.xyxy.cpu().tolist(),
            boxes.conf.cpu().tolist(),
            boxes.cls.cpu().tolist(),
        ):
            class_id = int(class_index)
            predictions.append({
                'media_id': media.id,
                'label': str(names.get(class_id, class_id)),
                'confidence': float(confidence),
                'bbox': [float(value) for value in xyxy],
                'bbox_format': 'xyxy',
                'normalized': False,
            })

    return {
        'dataset': int(dataset_id),
        'model': int(model_spec.get('registry_id') or 0),
        'predictions': predictions,
        'summary': {
            'total_images': len(ordered_media),
            'predicted_images': predicted_images,
            'total_predictions': len(predictions),
            'latency_ms': round((time.perf_counter() - started_at) * 1000, 2),
            'engine': 'local_ultralytics_fallback',
        },
    }


def _fallback_predictions(payload, remote_error):
    if not _local_fallback_enabled():
        raise remote_error
    logger.warning('Inference agent unavailable; using local Ultralytics fallback: %s', remote_error)
    try:
        return _local_predictions(payload)
    except Exception as exc:
        if isinstance(exc, AutoLabelInferenceError):
            local_error = exc
        else:
            local_error = AutoLabelInferenceError(str(exc))
        raise AutoLabelInferenceError(
            f'{remote_error} Local fallback also failed: {local_error}'
        ) from exc


def request_predictions(payload):
    inference_url = getattr(settings, 'INFERENCE_API_URL', '').rstrip('/')
    if not inference_url:
        return _fallback_predictions(
            payload,
            AutoLabelInferenceError('INFERENCE_API_URL is not configured on the backend.'),
        )
    headers = {}
    if settings.INFERENCE_AGENT_TOKEN:
        headers['Authorization'] = f'Bearer {settings.INFERENCE_AGENT_TOKEN}'
    try:
        response = requests.post(
            f'{inference_url}/v1/predict-dataset',
            json=payload,
            headers=headers,
            timeout=120,
        )
    except requests.RequestException as exc:
        return _fallback_predictions(
            payload,
            AutoLabelInferenceError(f'Inference server request failed: {exc}'),
        )
    if not response.ok:
        detail = response.text.strip() or response.reason
        remote_error = AutoLabelInferenceError(
            f'Inference agent returned HTTP {response.status_code}: {detail[:500]}'
        )
        if response.status_code >= 500:
            return _fallback_predictions(payload, remote_error)
        raise remote_error
    try:
        result = response.json()
    except ValueError as exc:
        raise AutoLabelInferenceError('Inference agent returned invalid JSON.') from exc
    if not isinstance(result, dict) or not isinstance(result.get('predictions', []), list):
        raise AutoLabelInferenceError('Inference agent response does not contain a predictions list.')
    return result


def prediction_bbox_data(prediction, media):
    bbox = prediction.get('bbox')
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4 or not media.width or not media.height:
        return None
    try:
        a, b, c, d = [float(value) for value in bbox]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (a, b, c, d)):
        return None
    if prediction.get('normalized'):
        a, c = a * media.width, c * media.width
        b, d = b * media.height, d * media.height
    if prediction.get('bbox_format', 'xywh') == 'xyxy':
        x, y, width, height = a, b, c - a, d - b
    else:
        width, height = c, d
        x, y = a - width / 2, b - height / 2
    x = max(0.0, min(x, float(media.width)))
    y = max(0.0, min(y, float(media.height)))
    width = max(0.0, min(width, float(media.width) - x))
    height = max(0.0, min(height, float(media.height) - y))
    if width <= 0 or height <= 0:
        return None
    return {'x': round(x, 2), 'y': round(y, 2), 'width': round(width, 2), 'height': round(height, 2)}


def prediction_polygon_data(prediction, media):
    points = prediction.get('points') or prediction.get('polygon')
    if not isinstance(points, (list, tuple)) or not media.width or not media.height:
        return None
    if points and isinstance(points[0], (list, tuple)):
        points = [coordinate for point in points for coordinate in point[:2]]
    if len(points) < 6 or len(points) % 2:
        return None
    try:
        values = [float(value) for value in points]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in values):
        return None
    normalized = prediction.get('normalized', False)
    clamped = []
    for index in range(0, min(len(values), 512), 2):
        x, y = values[index], values[index + 1]
        if normalized:
            x, y = x * media.width, y * media.height
        clamped.extend([
            round(max(0.0, min(x, float(media.width))), 2),
            round(max(0.0, min(y, float(media.height))), 2),
        ])
    return {'points': clamped} if len(clamped) >= 6 else None
