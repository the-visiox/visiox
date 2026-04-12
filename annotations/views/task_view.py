from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from annotations.models import Annotation, LabelingTask
from annotations.serializers import (
    AnnotationSerializer,
    JobAnnotationsReplaceSerializer,
    JobIssueSerializer,
    LabelingTaskSerializer,
)


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

    def _validate_class_labels_for_media(self, media, items):
        project_id = media.dataset.project_id
        for item in items:
            cl = item['class_label']
            if cl.project_id != project_id:
                raise ValidationError(
                    {'annotations': f'Class {cl.pk} does not belong to this project.'}
                )

    @extend_schema(
        methods=['GET'],
        responses={200: AnnotationSerializer(many=True)},
    )
    @extend_schema(
        methods=['PATCH'],
        request=JobAnnotationsReplaceSerializer,
        responses={200: AnnotationSerializer(many=True)},
    )
    @action(detail=True, methods=['get', 'patch'], url_path='annotations')
    def annotations(self, request, pk=None):
        """
        GET: list annotations for the job's media.
        PATCH: replace all annotations for that media (full snapshot save).
        """
        task = self.get_object()
        media = task.media
        if request.method == 'GET':
            qs = Annotation.objects.filter(media=media).select_related('class_label', 'annotator')
            return Response(AnnotationSerializer(qs, many=True).data)

        serializer = JobAnnotationsReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data['annotations']
        self._validate_class_labels_for_media(media, items)
        user = request.user
        with transaction.atomic():
            Annotation.objects.filter(media=media).delete()
            Annotation.objects.bulk_create(
                [
                    Annotation(
                        media=media,
                        class_label=item['class_label'],
                        annotator=user,
                        type=item['type'],
                        data=item['data'],
                        frame=item.get('frame', 0),
                        track_id=item.get('track_id'),
                    )
                    for item in items
                ]
            )
        qs = Annotation.objects.filter(media=media).select_related('class_label', 'annotator')
        return Response(AnnotationSerializer(qs, many=True).data)

    @extend_schema(
        methods=['GET'],
        responses={200: JobIssueSerializer(many=True)},
    )
    @extend_schema(
        methods=['POST'],
        request=JobIssueSerializer,
        responses={201: JobIssueSerializer},
    )
    @action(detail=True, methods=['get', 'post'], url_path='issues')
    def issues(self, request, pk=None):
        task = self.get_object()
        if request.method == 'GET':
            qs = task.issues.select_related('author').all()
            return Response(JobIssueSerializer(qs, many=True).data)
        serializer = JobIssueSerializer(
            data=request.data,
            context={'request': request, 'task': task},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

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
