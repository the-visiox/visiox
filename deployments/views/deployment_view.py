import requests

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

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
from datasets.models import Dataset


class ModelRegistryViewSet(viewsets.ModelViewSet):
    serializer_class = ModelRegistrySerializer
    queryset = ModelRegistry.objects.none()
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return ModelRegistry.objects.filter(
            project_access_q(self.request.user, 'training_job__project__')
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

        inference_url = getattr(settings, 'INFERENCE_API_URL', '').rstrip('/')
        if not inference_url:
            return Response(
                {'error': 'INFERENCE_API_URL is not configured on the backend.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        media_ids = request.data.get('media_ids') or []
        payload = {
            'model': {
                'registry_id': entry.id,
                'name': entry.name,
                'version': entry.version,
                'format': entry.format,
                'storage_key': entry.model_file.name if entry.model_file else None,
            },
            'dataset': {
                'id': dataset.id,
                'media_ids': media_ids,
            },
            'confidence': request.data.get('confidence'),
        }
        try:
            headers = {}
            if settings.INFERENCE_AGENT_TOKEN:
                headers['Authorization'] = f'Bearer {settings.INFERENCE_AGENT_TOKEN}'
            response = requests.post(
                f'{inference_url}/v1/predict-dataset',
                json=payload,
                headers=headers,
                timeout=120,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            return Response({'error': f'Inference server request failed: {exc}'}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(response.json())


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
