from drf_spectacular.utils import extend_schema
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from core.permissions import HasPerm
from training.models import ModelArchitecture, TrainingJob, Experiment, RunMetric
from training.serializers import (
    ModelArchitectureSerializer,
    TrainingJobSerializer,
    ExperimentSerializer,
    RunMetricSerializer,
)
from training.tasks import run_training_job


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
            project__team__members__user=user
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
            job.save(update_fields=['status'])
            task = run_training_job.delay(job.id)
            job.celery_task_id = task.id
            job.save(update_fields=['celery_task_id'])
            return Response(TrainingJobSerializer(job).data)

        if new_status == 'cancelled':
            if not request.user.has_perm('training.start_job'):
                return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
            from celery.result import AsyncResult
            if job.celery_task_id:
                AsyncResult(job.celery_task_id).revoke(terminate=True)
            job.status = 'cancelled'
            job.save(update_fields=['status'])
            return Response(TrainingJobSerializer(job).data)

        return super().partial_update(request, *args, **kwargs)

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
            job__project__team__members__user=user
        ).distinct().select_related('job')

    @extend_schema(responses={200: RunMetricSerializer(many=True)})
    @action(detail=True, methods=['get'])
    def metrics(self, request, pk=None):
        experiment = self.get_object()
        serializer = RunMetricSerializer(experiment.metrics.all(), many=True)
        return Response(serializer.data)
