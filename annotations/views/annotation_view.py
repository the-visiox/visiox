from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from annotations.models import Annotation
from annotations.serializers import (
    AnnotationSerializer,
    BulkAnnotationSerializer,
    JobAnnotationsReplaceSerializer,
)
from datasets.models import Media
from core.access import project_access_q


def _enqueue_dataset_label_cache_clear(dataset_id: int) -> None:
    from datasets.tasks import enqueue_dataset_label_cache_clear

    enqueue_dataset_label_cache_clear(dataset_id)


class AnnotationViewSet(viewsets.ModelViewSet):
    serializer_class = AnnotationSerializer
    queryset = Annotation.objects.none()

    def get_queryset(self):
        user = self.request.user
        qs = Annotation.objects.filter(
            project_access_q(user, 'media__dataset__project__')
        ).distinct().select_related('class_label', 'annotator', 'media')

        media_id = self.request.query_params.get('media')
        if media_id:
            qs = qs.filter(media_id=media_id)

        ann_type = self.request.query_params.get('type')
        if ann_type:
            qs = qs.filter(type=ann_type)

        return qs

    @extend_schema(request=BulkAnnotationSerializer, responses={201: AnnotationSerializer(many=True)})
    @action(detail=False, methods=['post'], url_path='bulk')
    def bulk_create(self, request):
        serializer = BulkAnnotationSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        created = serializer.save()
        return Response(
            AnnotationSerializer(created, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses={204: None})
    @action(detail=False, methods=['delete'], url_path='bulk-delete')
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': 'ids list required.'}, status=status.HTTP_400_BAD_REQUEST)
        Annotation.objects.filter(
            project_access_q(request.user, 'media__dataset__project__'),
            id__in=ids,
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MediaAnnotationsView(APIView):
    """
    GET  /api/media/<media_id>/annotations/ — list annotations for a media item.
    PUT  /api/media/<media_id>/annotations/ — replace ALL annotations for a media item (full snapshot save).
    """

    def _get_media(self, media_id):
        return get_object_or_404(Media, pk=media_id)

    @extend_schema(responses={200: AnnotationSerializer(many=True)})
    def get(self, _request, media_id):
        media = self._get_media(media_id)
        qs = Annotation.objects.filter(media=media).select_related('class_label', 'annotator')
        return Response(AnnotationSerializer(qs, many=True).data)

    @extend_schema(request=JobAnnotationsReplaceSerializer, responses={200: AnnotationSerializer(many=True)})
    def put(self, request, media_id):
        media = self._get_media(media_id)
        serializer = JobAnnotationsReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data['annotations']

        project_id = media.dataset.project_id
        for item in items:
            if item['class_label'].project_id != project_id:
                raise ValidationError(
                    {'annotations': f'Class {item["class_label"].pk} does not belong to this project.'}
                )

        user = request.user
        with transaction.atomic():
            Annotation.objects.filter(media=media).delete()
            Annotation.objects.bulk_create([
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
            ])
            if (media.metadata or {}).get('category') != 'augmented':
                media.dataset.invalidate_training_verification()
                transaction.on_commit(
                    lambda dataset_id=media.dataset_id: _enqueue_dataset_label_cache_clear(dataset_id)
                )
        qs = Annotation.objects.filter(media=media).select_related('class_label', 'annotator')
        return Response(AnnotationSerializer(qs, many=True).data)
