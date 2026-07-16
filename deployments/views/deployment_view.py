import math

import requests

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from annotations.colors import class_color_for_index
from annotations.models import Annotation, Class
from core.permissions import HasPerm
from core.access import project_access_q
from deployments.models import ModelRegistry, InferenceEndpoint, MonitoringLog, DriftAlert
from deployments.serializers import (
    ModelRegistrySerializer,
    InferenceEndpointSerializer,
    MonitoringLogSerializer,
    DriftAlertSerializer,
)
from deployments.tasks import check_endpoint_drift
from datasets.models import Dataset, Media


class InferenceAgentError(Exception):
    pass


def _inference_confidence(value) -> float:
    if value in (None, ''):
        return 0.25
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('confidence must be a number between 0 and 1.') from exc
    if not 0 <= confidence <= 1:
        raise ValueError('confidence must be between 0 and 1.')
    return confidence


def _request_dataset_predictions(entry, dataset, media_ids: list[int], confidence: float) -> dict:
    inference_url = getattr(settings, 'INFERENCE_API_URL', '').rstrip('/')
    if not inference_url:
        raise InferenceAgentError('INFERENCE_API_URL is not configured on the backend.')
    if not entry.model_file:
        raise InferenceAgentError('The selected model does not have a model artifact.')

    payload = {
        'model': {
            'registry_id': entry.id,
            'name': entry.name,
            'version': entry.version,
            'format': entry.format,
            'storage_key': entry.model_file.name,
        },
        'dataset': {
            'id': dataset.id,
            'media_ids': media_ids,
        },
        'confidence': confidence,
    }
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
        raise InferenceAgentError(f'Inference server request failed: {exc}') from exc
    if not response.ok:
        detail = response.text.strip() or response.reason
        raise InferenceAgentError(f'Inference agent returned HTTP {response.status_code}: {detail[:500]}')
    try:
        result = response.json()
    except ValueError as exc:
        raise InferenceAgentError('Inference agent returned invalid JSON.') from exc
    if not isinstance(result, dict) or not isinstance(result.get('predictions', []), list):
        raise InferenceAgentError('Inference agent response does not contain a predictions list.')
    return result


def _prediction_annotation_data(prediction: dict, media: Media) -> dict | None:
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
        x, y = a, b
        width, height = c - a, d - b
    else:
        width, height = c, d
        x, y = a - (width / 2), b - (height / 2)
    x = max(0.0, min(x, float(media.width)))
    y = max(0.0, min(y, float(media.height)))
    width = max(0.0, min(width, float(media.width) - x))
    height = max(0.0, min(height, float(media.height) - y))
    if width <= 0 or height <= 0:
        return None
    return {
        'x': round(x, 2),
        'y': round(y, 2),
        'width': round(width, 2),
        'height': round(height, 2),
    }


class ModelRegistryViewSet(viewsets.ModelViewSet):
    serializer_class = ModelRegistrySerializer
    queryset = ModelRegistry.objects.none()
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return ModelRegistry.objects.filter(
            project_access_q(self.request.user, 'training_job__project__')
            | Q(training_job__isnull=True, created_by=self.request.user)
        ).distinct().select_related('created_by', 'training_job')

    @extend_schema(responses={200: ModelRegistrySerializer})
    @action(detail=True, methods=['post'])
    def rollback(self, request, pk=None):
        entry = self.get_object()
        previous = ModelRegistry.objects.filter(
            training_job=entry.training_job,
            created_at__lt=entry.created_at,
        ).order_by('-created_at').first()

        if not previous:
            return Response({'error': 'No previous version to roll back to.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'message': f'Rolled back from v{entry.version} to v{previous.version}',
            'active_version': ModelRegistrySerializer(previous).data,
        })

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=['post'], url_path='predict-dataset')
    def predict_dataset(self, request, pk=None):
        entry = self.get_object()
        dataset_id = request.data.get('dataset')
        if not dataset_id:
            return Response({'error': 'dataset is required.'}, status=status.HTTP_400_BAD_REQUEST)

        dataset = Dataset.objects.filter(
            project_access_q(request.user, 'project__'),
            pk=dataset_id,
        ).first()
        if not dataset:
            return Response({'error': 'Dataset not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            confidence = _inference_confidence(request.data.get('confidence'))
            media_ids = [int(media_id) for media_id in (request.data.get('media_ids') or [])]
            result = _request_dataset_predictions(entry, dataset, media_ids, confidence)
        except (TypeError, ValueError) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except InferenceAgentError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(result)

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=['post'], url_path='label-dataset')
    def label_dataset(self, request, pk=None):
        entry = self.get_object()
        dataset_id = request.data.get('dataset')
        dataset = Dataset.objects.filter(
            project_access_q(request.user, 'project__'),
            pk=dataset_id,
        ).select_related('project').first()
        if not dataset:
            return Response({'error': 'Dataset not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            confidence = _inference_confidence(request.data.get('confidence'))
            requested_ids = [int(media_id) for media_id in (request.data.get('media_ids') or [])]
        except (TypeError, ValueError) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        media_query = dataset.media_files.filter(type='image').only('id', 'width', 'height', 'dataset_id')
        if requested_ids:
            media_query = media_query.filter(id__in=requested_ids)
        media_by_id = {media.id: media for media in media_query}
        if requested_ids and set(media_by_id) != set(requested_ids):
            return Response(
                {'error': 'One or more media IDs do not belong to this dataset.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        media_ids = list(media_by_id)
        if not media_ids:
            return Response({'error': 'No images are available for model labeling.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = _request_dataset_predictions(entry, dataset, media_ids, confidence)
        except InferenceAgentError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        classes = list(Class.objects.filter(project=dataset.project).order_by('id'))
        class_by_name = {class_obj.name.strip().casefold(): class_obj for class_obj in classes}
        annotations = []
        skipped = 0
        for prediction in result.get('predictions', []):
            try:
                media = media_by_id[int(prediction.get('media_id'))]
            except (KeyError, TypeError, ValueError):
                skipped += 1
                continue
            label = str(prediction.get('label') or '').strip()
            if not label:
                skipped += 1
                continue
            class_obj = class_by_name.get(label.casefold())
            if class_obj is None:
                class_obj, _ = Class.objects.get_or_create(
                    project=dataset.project,
                    name=label,
                    defaults={'color': class_color_for_index(len(class_by_name))},
                )
                class_by_name[label.casefold()] = class_obj
            box_data = _prediction_annotation_data(prediction, media)
            if box_data is None:
                skipped += 1
                continue
            annotations.append(Annotation(
                media=media,
                class_label=class_obj,
                annotator=request.user,
                type='bbox',
                data={
                    **box_data,
                    'confidence': prediction.get('confidence'),
                    'source': 'model',
                    'model_registry_id': entry.id,
                    'model_name': entry.name,
                    'model_version': entry.version,
                },
                frame=0,
            ))

        with transaction.atomic():
            Annotation.objects.filter(
                media_id__in=media_ids,
                data__source='model',
                data__model_registry_id=entry.id,
            ).delete()
            if annotations:
                Annotation.objects.bulk_create(annotations, batch_size=1000)
            dataset.invalidate_training_verification()
            from datasets.tasks import enqueue_dataset_label_cache_clear
            transaction.on_commit(lambda: enqueue_dataset_label_cache_clear(dataset.id))

        return Response({
            'dataset': dataset.id,
            'model': entry.id,
            'processed_images': len(media_ids),
            'labeled_images': len({annotation.media_id for annotation in annotations}),
            'saved_annotations': len(annotations),
            'skipped_predictions': skipped,
            'summary': result.get('summary') or {},
        })


class InferenceEndpointViewSet(viewsets.ModelViewSet):
    serializer_class = InferenceEndpointSerializer
    queryset = InferenceEndpoint.objects.none()

    def get_queryset(self):
        return InferenceEndpoint.objects.filter(
            project_access_q(self.request.user, 'registry_entry__training_job__project__')
        ).distinct().select_related('registry_entry', 'created_by')

    def partial_update(self, request, *args, **kwargs):
        endpoint = self.get_object()
        new_status = request.data.get('status')

        if new_status == 'active':
            if not request.user.has_perm('deployments.start_endpoint'):
                return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
            if endpoint.status == 'active':
                return Response({'error': 'Endpoint is already active.'}, status=status.HTTP_400_BAD_REQUEST)
            endpoint.status = 'active'
            endpoint.save(update_fields=['status'])
            return Response(InferenceEndpointSerializer(endpoint).data)

        if new_status == 'inactive':
            if not request.user.has_perm('deployments.stop_endpoint'):
                return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
            endpoint.status = 'inactive'
            endpoint.save(update_fields=['status'])
            return Response(InferenceEndpointSerializer(endpoint).data)

        return super().partial_update(request, *args, **kwargs)

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=['post'])
    def trigger_drift_check(self, request, pk=None):
        endpoint = self.get_object()
        task = check_endpoint_drift.delay(endpoint.id)
        return Response({'task_id': task.id, 'message': 'Drift check queued.'})

    @extend_schema(responses={200: MonitoringLogSerializer(many=True)})
    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        endpoint = self.get_object()
        logs = endpoint.logs.all()[:100]
        return Response(MonitoringLogSerializer(logs, many=True).data)

    @extend_schema(responses={200: DriftAlertSerializer(many=True)})
    @action(detail=True, methods=['get'])
    def alerts(self, request, pk=None):
        endpoint = self.get_object()
        alerts = endpoint.drift_alerts.filter(is_resolved=False)
        return Response(DriftAlertSerializer(alerts, many=True).data)

    @extend_schema(responses={201: MonitoringLogSerializer})
    @action(detail=True, methods=['post'])
    def log_prediction(self, request, pk=None):
        endpoint = self.get_object()
        serializer = MonitoringLogSerializer(data={**request.data, 'endpoint': endpoint.id})
        serializer.is_valid(raise_exception=True)
        log = serializer.save()

        if log.confidence < endpoint.confidence_threshold:
            log.is_flagged = True
            log.flagged_reason = 'below_threshold'
            log.save(update_fields=['is_flagged', 'flagged_reason'])

            from annotations.models import LabelingTask
            from datasets.models import Media

        return Response(MonitoringLogSerializer(log).data, status=status.HTTP_201_CREATED)


class MonitoringLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MonitoringLogSerializer
    queryset = MonitoringLog.objects.none()

    def get_queryset(self):
        return MonitoringLog.objects.filter(
            project_access_q(self.request.user, 'endpoint__registry_entry__training_job__project__')
        ).distinct()


class DriftAlertViewSet(viewsets.ModelViewSet):
    serializer_class = DriftAlertSerializer
    queryset = DriftAlert.objects.none()
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return DriftAlert.objects.filter(
            project_access_q(self.request.user, 'endpoint__registry_entry__training_job__project__')
        ).distinct()

    @extend_schema(responses={200: DriftAlertSerializer})
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        alert = self.get_object()
        alert.is_resolved = True
        alert.resolved_at = timezone.now()
        alert.save(update_fields=['is_resolved', 'resolved_at'])
        return Response(DriftAlertSerializer(alert).data)
