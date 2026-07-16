"""
Celery tasks for deployment monitoring and active learning feedback.
"""
from celery import shared_task
from django.utils import timezone


@shared_task
def check_endpoint_drift(endpoint_id: int):
    """
    Analyse recent MonitoringLogs for an endpoint.
    Raises a DriftAlert if mean confidence drops below the endpoint threshold.
    Low-confidence predictions are flagged back to the annotation queue.
    """
    from deployments.models import InferenceEndpoint, MonitoringLog, DriftAlert

    try:
        endpoint = InferenceEndpoint.objects.get(pk=endpoint_id)
    except InferenceEndpoint.DoesNotExist:
        return {'error': f'Endpoint {endpoint_id} not found'}

    window_minutes = 60
    since = timezone.now() - timezone.timedelta(minutes=window_minutes)
    recent_logs = MonitoringLog.objects.filter(endpoint=endpoint, timestamp__gte=since)

    count = recent_logs.count()
    if count == 0:
        return {'endpoint': endpoint_id, 'message': 'No logs in window'}

    mean_confidence = sum(log.confidence for log in recent_logs) / count
    threshold = endpoint.confidence_threshold

    result = {
        'endpoint': endpoint_id,
        'window_minutes': window_minutes,
        'log_count': count,
        'mean_confidence': round(mean_confidence, 4),
        'threshold': threshold,
    }

    if mean_confidence < threshold:
        alert = DriftAlert.objects.create(
            endpoint=endpoint,
            severity='high' if mean_confidence < threshold * 0.8 else 'medium',
            metric='mean_confidence',
            threshold=threshold,
            observed_value=mean_confidence,
            details={'log_count': count, 'window_minutes': window_minutes},
        )
        result['alert_id'] = alert.id

        low_conf_logs = recent_logs.filter(confidence__lt=threshold, is_flagged=False)
        low_conf_logs.update(is_flagged=True, flagged_reason='drift_detected')
        result['flagged_count'] = low_conf_logs.count()

    return result


@shared_task
def deliver_webhook(webhook_id: int, event: str, payload: dict):
    """Send a webhook POST to the registered URL."""
    import hmac
    import hashlib
    import json
    import requests
    from billing.models import Webhook

    try:
        webhook = Webhook.objects.get(pk=webhook_id, is_active=True)
    except Webhook.DoesNotExist:
        return {'error': f'Webhook {webhook_id} not found'}

    if event not in webhook.events:
        return {'skipped': True, 'reason': 'event not subscribed'}

    body = json.dumps({'event': event, 'data': payload})
    sig = hmac.new(webhook.secret.encode(), body.encode(), hashlib.sha256).hexdigest()

    try:
        resp = requests.post(
            webhook.url,
            data=body,
            headers={
                'Content-Type': 'application/json',
                'X-Visiox-Signature': sig,
                'X-Visiox-Event': event,
            },
            timeout=10,
        )
        return {'status_code': resp.status_code}
    except Exception as exc:
        return {'error': str(exc)}
