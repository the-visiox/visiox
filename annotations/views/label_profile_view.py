from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from annotations.models import Class
from datasets.models import Dataset, Media, MediaLabelProfile
from datasets.standalone import image_media_for_frame


class LabelItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=255)
    color = serializers.CharField(max_length=7)


class LabelProfileWriteSerializer(serializers.Serializer):
    labels = LabelItemSerializer(many=True)


def _media_for_user(_request, media_id: int) -> Media:
    return get_object_or_404(Media, pk=media_id)


def _dataset_for_user(_request, dataset_id: int) -> Dataset:
    return get_object_or_404(Dataset, pk=dataset_id)


def _validate_labels_for_media(media: Media, labels: list[dict]) -> None:
    project_id = media.dataset.project_id
    ids = [item['id'] for item in labels]
    if len(set(ids)) != len(ids):
        raise serializers.ValidationError({'labels': 'Duplicate label ids are not allowed.'})

    qs = Class.objects.filter(id__in=ids, project_id=project_id)
    found = set(qs.values_list('id', flat=True))
    missing = sorted(set(ids) - found)
    if missing:
        raise serializers.ValidationError({'labels': f'Unknown class ids for this project: {missing}'})


class MediaLabelProfileView(APIView):
    """GET/PUT per-image label roster stored in Postgres (JSON on ``MediaLabelProfile``)."""

    @extend_schema(responses={200: LabelProfileWriteSerializer})
    def get(self, request, media_id):
        media = _media_for_user(request, media_id)
        profile, _created = MediaLabelProfile.objects.get_or_create(media=media, defaults={'labels': []})
        return Response({'labels': profile.labels or []})

    @extend_schema(request=LabelProfileWriteSerializer, responses={200: LabelProfileWriteSerializer})
    def put(self, request, media_id):
        media = _media_for_user(request, media_id)
        serializer = LabelProfileWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        labels = serializer.validated_data['labels']
        _validate_labels_for_media(media, labels)

        profile, _created = MediaLabelProfile.objects.get_or_create(media=media, defaults={'labels': []})
        profile.labels = labels
        profile.save(update_fields=['labels', 'updated_at'])
        return Response({'labels': profile.labels})


class DatasetFrameLabelProfileView(APIView):
    """GET/PUT label roster for a dataset frame (native mode) — resolves to underlying ``Media``."""

    @extend_schema(responses={200: LabelProfileWriteSerializer})
    def get(self, request, dataset_id, frame_num):
        dataset = _dataset_for_user(request, dataset_id)
        media = image_media_for_frame(dataset, int(frame_num))
        if media is None:
            return Response(
                {'detail': f'Frame {frame_num} not found in dataset {dataset_id}.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        profile, _created = MediaLabelProfile.objects.get_or_create(media=media, defaults={'labels': []})
        return Response({'labels': profile.labels or []})

    @extend_schema(request=LabelProfileWriteSerializer, responses={200: LabelProfileWriteSerializer})
    def put(self, request, dataset_id, frame_num):
        dataset = _dataset_for_user(request, dataset_id)
        media = image_media_for_frame(dataset, int(frame_num))
        if media is None:
            return Response(
                {'detail': f'Frame {frame_num} not found in dataset {dataset_id}.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = LabelProfileWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        labels = serializer.validated_data['labels']
        _validate_labels_for_media(media, labels)

        profile, _created = MediaLabelProfile.objects.get_or_create(media=media, defaults={'labels': []})
        profile.labels = labels
        profile.save(update_fields=['labels', 'updated_at'])
        return Response({'labels': profile.labels})
