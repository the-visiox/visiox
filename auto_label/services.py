import math

import requests
from django.conf import settings


class AutoLabelInferenceError(RuntimeError):
    pass


def inference_confidence(value):
    if value in (None, ''):
        return 0.25
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('confidence must be a number between 0 and 1.') from exc
    if not 0 <= confidence <= 1:
        raise ValueError('confidence must be between 0 and 1.')
    return confidence


def request_predictions(payload):
    inference_url = getattr(settings, 'INFERENCE_API_URL', '').rstrip('/')
    if not inference_url:
        raise AutoLabelInferenceError('INFERENCE_API_URL is not configured on the backend.')
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
        raise AutoLabelInferenceError(f'Inference server request failed: {exc}') from exc
    if not response.ok:
        detail = response.text.strip() or response.reason
        raise AutoLabelInferenceError(f'Inference agent returned HTTP {response.status_code}: {detail[:500]}')
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
