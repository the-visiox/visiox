from drf_spectacular.utils import extend_schema
from rest_framework import viewsets, status
from rest_framework.decorators import action
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from core.permissions import HasPerm
from core.access import project_access_q
from training.models import ModelArchitecture, TrainingJob, Experiment, RunMetric
from training.serializers import (
    ModelArchitectureSerializer,
    TrainingJobSerializer,
    ExperimentSerializer,
    RunMetricSerializer,
    KNOWN_TRAINING_ARTIFACTS,
)
from training.tasks import run_training_job
from training.agent import TrainingAgentError, cancel_training_job, get_training_job_status, save_artifact


def _callback_authorized(request):
    expected = settings.TRAINING_CALLBACK_TOKEN
    return bool(expected) and request.headers.get('Authorization') == f'Bearer {expected}'


SPLIT_METRIC_ALIASES = {
    'train': ('train', 'training'),
    'valid': ('valid', 'val', 'validation', 'dev'),
    'test': ('test',),
}
SCORE_METRIC_ALIASES = {
    'f1': ('f1', 'f1_score'),
    'precision': ('precision', 'metrics/precision(B)'),
    'recall': ('recall', 'metrics/recall(B)'),
    'map50': ('map50', 'mAP50', 'best_map50', 'metrics/mAP50(B)'),
    'map75': ('map75', 'mAP75', 'best_map75', 'mAP75(B)', 'metrics/mAP75(B)'),
}


def _extract_score_metrics(values):
    if not isinstance(values, dict):
        return {}
    scores = {}
    for canonical_metric, metric_aliases in SCORE_METRIC_ALIASES.items():
        for metric_alias in metric_aliases:
            value = values.get(metric_alias)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                scores[canonical_metric] = value
                break
    if 'f1' not in scores and 'precision' in scores and 'recall' in scores:
        denominator = scores['precision'] + scores['recall']
        scores['f1'] = 2 * scores['precision'] * scores['recall'] / denominator if denominator else 0.0
    return scores


def _normalize_split_metrics(payload):
    """Return the canonical train/valid/test score object accepted from GPU agents."""
    if not isinstance(payload, dict):
        return {}

    containers = [payload]
    for key in ('split_metrics', 'splits', 'by_split', 'summary'):
        if isinstance(payload.get(key), dict):
            containers.insert(0, payload[key])

    normalized = {}
    for canonical_split, split_aliases in SPLIT_METRIC_ALIASES.items():
        split_values = None
        for container in containers:
            for split_alias in split_aliases:
                if isinstance(container.get(split_alias), dict):
                    split_values = container[split_alias]
                    break
            if split_values is not None:
                break
        if split_values is None:
            continue

        scores = _extract_score_metrics(split_values)
        if scores:
            normalized[canonical_split] = scores

    # Current GPU agents expose final validation metrics at the top level (and
    # sometimes under "latest") instead of an explicit "valid" object.
    if 'valid' not in normalized:
        validation_scores = _extract_score_metrics(payload)
        if not validation_scores and isinstance(payload.get('latest'), dict):
            validation_scores = _extract_score_metrics(payload['latest'])
        if validation_scores:
            normalized['valid'] = validation_scores
    return normalized


def _coerce_metrics_payload(payload):
    """
    Accept both callback payload shapes:
    1. Flat fields at the top level.
    2. Nested training metrics under payload["metrics"].
    """
    nested_metrics = payload.get('metrics') if isinstance(payload.get('metrics'), dict) else {}
    merged = {**nested_metrics, **payload}
    merged.pop('metrics', None)

    extra = dict(payload.get('extra') or {})
    for key in (
        'precision',
        'recall',
        'total_epochs',
        'stage',
        'message',
        'progress_percent',
        'eta_seconds',
        'gpu_memory_mb',
        'gpu_utilization',
        'learning_rate',
    ):
        if key in nested_metrics and key not in extra:
            extra[key] = nested_metrics[key]
        if key in payload:
            extra[key] = payload[key]
    split_metrics = {}
    for source in (extra, nested_metrics, payload):
        for split, scores in _normalize_split_metrics(source).items():
            split_metrics.setdefault(split, {}).update(scores)
    if split_metrics:
        extra['split_metrics'] = split_metrics
    merged['extra'] = extra
    return merged


def _normalize_callback_artifacts(current_artifacts, callback_artifacts):
    artifacts = dict(current_artifacts or {})
    if isinstance(callback_artifacts, dict):
        return {**artifacts, **callback_artifacts}
    if not isinstance(callback_artifacts, list):
        return artifacts
    for item in callback_artifacts:
        if not isinstance(item, dict):
            continue
        filename = item.get('filename') or item.get('name')
        if not filename:
            continue
        metadata = dict(artifacts.get(filename) or {})
        for key in ('storage_key', 'size', 'format', 'optional'):
            if item.get(key) is not None:
                metadata[key] = item[key]
        artifacts[filename] = metadata
    return artifacts


def _discover_uploaded_artifacts(job):
    from core.storage import get_artifacts_storage

    storage = get_artifacts_storage()
    artifacts = dict(job.artifacts or {})
    for name in KNOWN_TRAINING_ARTIFACTS:
        key = f'training-jobs/{job.id}/artifacts/{name}'
        try:
            if not storage.exists(key):
                continue
            metadata = dict(artifacts.get(name) or {})
            metadata['storage_key'] = key
            try:
                metadata['size'] = storage.size(key)
            except (NotImplementedError, OSError, ValueError):
                pass
            artifacts[name] = metadata
        except (NotImplementedError, ValueError):
            continue
    return artifacts


def _sync_agent_status(job):
    if job.status not in ('queued', 'running'):
        return job
    try:
        agent_status = get_training_job_status(job)
    except TrainingAgentError:
        return job
    if not agent_status:
        return job
    status_value = agent_status.get('status')
    update_fields = []
    if agent_status.get('agent_job_id') and job.agent_job_id != agent_status['agent_job_id']:
        job.agent_job_id = agent_status['agent_job_id']
        update_fields.append('agent_job_id')
    if status_value in ('queued', 'running') and job.status != status_value:
        job.status = status_value
        update_fields.append('status')
    if status_value == 'completed':
        job.status = 'completed'
        job.error_message = ''
        job.finished_at = job.finished_at or timezone.now()
        update_fields.extend(['status', 'error_message', 'finished_at'])
    elif status_value == 'failed':
        job.status = 'failed'
        job.error_message = agent_status.get('error_message') or 'GPU training failed.'
        job.finished_at = timezone.now()
        update_fields.extend(['status', 'error_message', 'finished_at'])
    elif status_value == 'cancelled':
        job.status = 'cancelled'
        job.finished_at = timezone.now()
        update_fields.extend(['status', 'finished_at'])
    if update_fields:
        job.save(update_fields=sorted(set(update_fields)))
    return job


class ModelArchitectureViewSet(viewsets.ModelViewSet):
    serializer_class = ModelArchitectureSerializer
    queryset = ModelArchitecture.objects.all()

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAdminUser()]
        return [IsAuthenticated()]


class TrainingJobViewSet(viewsets.ModelViewSet):
    serializer_class = TrainingJobSerializer
    queryset = TrainingJob.objects.none()

    def get_queryset(self):
        user = self.request.user
        return TrainingJob.objects.filter(
            project_access_q(user, 'project__')
        ).distinct().select_related('architecture', 'created_by', 'project', 'dataset')

    def partial_update(self, request, *args, **kwargs):
        job = self.get_object()
        new_status = request.data.get('status')

        if new_status == 'queued':
            if not request.user.has_perm('training.start_job'):
                return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
            if job.status not in ('pending', 'failed'):
                return Response(
                    {'error': f'Cannot start a job with status "{job.status}".'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            job.status = 'queued'
            job.error_message = ''
            job.finished_at = None
            job.started_at = None
            job.agent_job_id = ''
            job.save(update_fields=['status', 'error_message', 'finished_at', 'started_at', 'agent_job_id'])
            task = run_training_job.delay(job.id)
            job.celery_task_id = task.id
            job.save(update_fields=['celery_task_id'])
            return Response(TrainingJobSerializer(job).data)

        if new_status == 'cancelled':
            if not request.user.has_perm('training.stop_job'):
                return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
            try:
                cancel_training_job(job)
            except TrainingAgentError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
            job.status = 'cancelled'
            job.finished_at = timezone.now()
            job.save(update_fields=['status', 'finished_at'])
            return Response(TrainingJobSerializer(job).data)

        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        job = self.get_object()
        if job.status in ('queued', 'running'):
            return Response(
                {'error': 'Cancel the active training run before deleting it.'},
                status=status.HTTP_409_CONFLICT,
            )
        job.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def retrieve(self, request, *args, **kwargs):
        job = _sync_agent_status(self.get_object())
        return Response(self.get_serializer(job).data)

    @extend_schema(responses={200: ExperimentSerializer(many=True)})
    @action(detail=True, methods=['get'])
    def experiments(self, request, pk=None):
        job = self.get_object()
        serializer = ExperimentSerializer(job.experiments.all(), many=True)
        return Response(serializer.data)


class ExperimentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ExperimentSerializer
    queryset = Experiment.objects.none()

    def get_queryset(self):
        user = self.request.user
        return Experiment.objects.filter(
            project_access_q(user, 'job__project__')
        ).distinct().select_related('job')

    @extend_schema(responses={200: RunMetricSerializer(many=True)})
    @action(detail=True, methods=['get'])
    def metrics(self, request, pk=None):
        experiment = self.get_object()
        serializer = RunMetricSerializer(experiment.metrics.all(), many=True)
        return Response(serializer.data)


class TrainingCallbackViewSet(viewsets.ViewSet):
    """Bearer-authenticated machine endpoints used only by the GPU agent."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def _job(self, request, job_id):
        if not _callback_authorized(request):
            return None, Response({'error': 'Invalid callback token.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            return TrainingJob.objects.get(pk=job_id), None
        except TrainingJob.DoesNotExist:
            return None, Response({'error': 'Training job not found.'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'], url_path=r'(?P<job_id>\d+)/metrics')
    def metrics(self, request, job_id=None):
        job, error = self._job(request, job_id)
        if error:
            return error
        experiment = job.experiments.first()
        if experiment is None:
            experiment = Experiment.objects.create(job=job, name=f'Run {job.name}')
        payload = _coerce_metrics_payload(request.data)
        extra = payload.get('extra') or {}
        RunMetric.objects.update_or_create(
            experiment=experiment, epoch=payload.get('epoch', 0), step=payload.get('step', 0),
            defaults={
                'loss': payload.get('loss'), 'val_loss': payload.get('val_loss'),
                'map50': payload.get('map50', payload.get('map')),
                'map75': payload.get('map75'), 'f1': payload.get('f1'),
                'accuracy': payload.get('accuracy'), 'extra': extra,
            },
        )
        if job.status in ('pending', 'queued'):
            job.status = 'running'
            job.started_at = job.started_at or timezone.now()
            job.save(update_fields=['status', 'started_at'])
        return Response({'ok': True})

    @action(detail=False, methods=['post'], url_path=r'(?P<job_id>\d+)/heartbeat')
    def heartbeat(self, request, job_id=None):
        job, error = self._job(request, job_id)
        if error:
            return error
        job.last_heartbeat_at = timezone.now()
        if job.status == 'queued':
            job.status = 'running'
            job.started_at = job.started_at or timezone.now()
        job.save(update_fields=['last_heartbeat_at', 'status', 'started_at'])
        return Response({'ok': True})

    @action(detail=False, methods=['post'], url_path=r'(?P<job_id>\d+)/complete')
    def complete(self, request, job_id=None):
        job, error = self._job(request, job_id)
        if error:
            return error
        with transaction.atomic():
            job.status = 'completed'
            job.finished_at = timezone.now()
            job.error_message = ''
            job.artifacts = _normalize_callback_artifacts(job.artifacts, request.data.get('artifacts'))
            job.artifacts = _discover_uploaded_artifacts(job)
            job.save(update_fields=['status', 'finished_at', 'error_message', 'artifacts'])
            from deployments.models import ModelRegistry
            best_pt = (job.artifacts or {}).get('best.pt', {})
            if isinstance(best_pt, dict) and best_pt.get('storage_key'):
                latest_metric = job.experiments.first()
                latest_metric = latest_metric.metrics.last() if latest_metric else None
                metrics = request.data.get('metrics') if isinstance(request.data.get('metrics'), dict) else {}
                completion_split_metrics = _normalize_split_metrics(metrics)
                if latest_metric:
                    metrics = {
                        **metrics,
                        'loss': latest_metric.loss,
                        'val_loss': latest_metric.val_loss,
                        'map50': latest_metric.map50,
                        'map75': latest_metric.map75,
                        'f1': latest_metric.f1,
                        **(latest_metric.extra or {}),
                    }
                split_metrics = _normalize_split_metrics(metrics)
                split_metrics.update(completion_split_metrics)
                if split_metrics:
                    metrics = {**metrics, 'split_metrics': split_metrics}
                registry, _ = ModelRegistry.objects.get_or_create(
                    training_job=job,
                    format='pytorch',
                    defaults={
                        'name': job.name,
                        'version': f'1.0.{job.id}',
                        'created_by': job.created_by,
                    },
                )
                registry.model_file.name = best_pt['storage_key']
                registry.file_size = best_pt.get('size')
                registry.metrics = metrics
                registry.changelog = f'Automatically registered from training job {job.id}.'
                registry.save()
        return Response({'ok': True})

    @action(detail=False, methods=['post'], url_path=r'(?P<job_id>\d+)/failed')
    def failed(self, request, job_id=None):
        job, error = self._job(request, job_id)
        if error:
            return error
        job.status = 'failed'
        job.error_message = (
            request.data.get('error_message')
            or request.data.get('error')
            or request.data.get('message')
            or 'GPU training failed.'
        )
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at'])
        return Response({'ok': True})

    @action(detail=False, methods=['put'], url_path=r'(?P<job_id>\d+)/artifacts/(?P<filename>[^/]+)')
    def artifact(self, request, job_id=None, filename=None):
        job, error = self._job(request, job_id)
        if error:
            return error
        content = ContentFile(request.body, name=filename)
        return Response(save_artifact(job, filename, content))
