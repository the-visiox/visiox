from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from annotations.models import LabelingTask
from annotations.serializers import LabelingTaskSerializer


class LabelingTaskViewSet(viewsets.ModelViewSet):
    serializer_class = LabelingTaskSerializer
    queryset = LabelingTask.objects.none()

    def get_queryset(self):
        user = self.request.user
        qs = LabelingTask.objects.filter(
            media__dataset__project__team__members__user=user
        ).distinct().select_related('media', 'assigned_to')

        task_status = self.request.query_params.get('status')
        if task_status:
            qs = qs.filter(status=task_status)
        return qs

    @extend_schema(responses={200: LabelingTaskSerializer})
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        task = self.get_object()
        if task.status != 'pending':
            return Response({'error': 'Only pending tasks can be started.'}, status=status.HTTP_400_BAD_REQUEST)
        task.status = 'in_progress'
        task.assigned_to = request.user
        task.save()
        return Response(LabelingTaskSerializer(task, context={'request': request}).data)

    @extend_schema(responses={200: LabelingTaskSerializer})
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        task = self.get_object()
        if task.status != 'in_progress':
            return Response({'error': 'Only in-progress tasks can be completed.'}, status=status.HTTP_400_BAD_REQUEST)
        task.status = 'completed'
        task.completed_at = timezone.now()
        task.save()
        return Response(LabelingTaskSerializer(task, context={'request': request}).data)

    @extend_schema(responses={200: LabelingTaskSerializer})
    @action(detail=True, methods=['post'])
    def submit_for_review(self, request, pk=None):
        task = self.get_object()
        if task.status != 'completed':
            return Response({'error': 'Only completed tasks can be submitted for review.'}, status=status.HTTP_400_BAD_REQUEST)
        task.status = 'review'
        task.save()
        return Response(LabelingTaskSerializer(task, context={'request': request}).data)

    @extend_schema(responses={200: LabelingTaskSerializer})
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        task = self.get_object()
        task.status = 'approved'
        task.save()
        return Response(LabelingTaskSerializer(task, context={'request': request}).data)

    @extend_schema(responses={200: LabelingTaskSerializer})
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        task = self.get_object()
        task.status = 'rejected'
        task.save()
        return Response(LabelingTaskSerializer(task, context={'request': request}).data)
