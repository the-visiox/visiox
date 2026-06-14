from pathlib import Path

from django.core.files import File
from django.db import transaction
from django.db.models import F
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from annotations.models import Annotation, Class
from datasets.models import Dataset, Media, MediaLabelProfile
from dataverse.models import DataverseProject
from dataverse.serializers import (
    DataverseForkSerializer,
    DataverseProjectSerializer,
    DataverseShareSerializer,
)
from projects.models import Project


class DataverseProjectViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = DataverseProjectSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = [
        'title',
        'summary',
        'tags',
        'source_project__name',
        'source_project__description',
        'owner__username',
    ]
    ordering_fields = ['updated_at', 'created_at', 'fork_count', 'view_count', 'title']
    ordering = ['-updated_at']

    def get_queryset(self):
        return (
            DataverseProject.objects
            .filter(is_public=True)
            .select_related('source_project', 'source_project__team', 'owner')
            .prefetch_related('source_project__datasets', 'source_project__classes')
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        DataverseProject.objects.filter(pk=instance.pk).update(view_count=F('view_count') + 1)
        instance.refresh_from_db(fields=['view_count'])
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = DataverseShareSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        project = serializer.validated_data['project']
        listing, _ = DataverseProject.objects.update_or_create(
            source_project=project,
            defaults={
                'owner': request.user,
                'title': serializer.validated_data.get('title') or project.name,
                'summary': serializer.validated_data.get('summary') or project.description or '',
                'tags': serializer.validated_data.get('tags', []),
                'license': serializer.validated_data.get('license') or 'Community',
                'is_public': serializer.validated_data.get('is_public', True),
            },
        )
        return Response(
            DataverseProjectSerializer(listing, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'])
    def fork(self, request, pk=None):
        listing = self.get_object()
        serializer = DataverseForkSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            forked = self._fork_project(
                source=listing.source_project,
                team=serializer.validated_data['team'],
                user=request.user,
                name=serializer.validated_data.get('name') or f'{listing.source_project.name} Fork',
            )
            DataverseProject.objects.filter(pk=listing.pk).update(fork_count=F('fork_count') + 1)

        return Response({'project_id': forked.id, 'name': forked.name}, status=status.HTTP_201_CREATED)

    def _fork_project(self, *, source: Project, team, user, name: str) -> Project:
        forked_project = Project.objects.create(
            team=team,
            owner=user,
            name=name.strip(),
            task_type=source.task_type,
            description=source.description,
        )

        class_map: dict[int, Class] = {}
        for class_label in source.classes.all():
            class_map[class_label.id] = Class.objects.create(
                project=forked_project,
                name=class_label.name,
                color=class_label.color,
                attributes=class_label.attributes,
            )

        for source_dataset in source.datasets.all().prefetch_related('media_files__annotations', 'media_files__label_profile'):
            forked_dataset = Dataset.objects.create(
                project=forked_project,
                name=source_dataset.name,
                description=source_dataset.description,
                version=source_dataset.version,
            )
            media_map: dict[int, Media] = {}
            for source_media in source_dataset.media_files.all():
                forked_media = Media(
                    dataset=forked_dataset,
                    type=source_media.type,
                    original_filename=source_media.original_filename,
                    width=source_media.width,
                    height=source_media.height,
                    file_size=source_media.file_size,
                    metadata=source_media.metadata,
                )
                if source_media.file:
                    source_media.file.open('rb')
                    try:
                        forked_media.file.save(Path(source_media.file.name).name, File(source_media.file), save=False)
                    finally:
                        source_media.file.close()
                forked_media.save()
                media_map[source_media.id] = forked_media

                label_profile = getattr(source_media, 'label_profile', None)
                if label_profile:
                    MediaLabelProfile.objects.create(media=forked_media, labels=label_profile.labels)

            annotations = []
            for source_media_id, forked_media in media_map.items():
                for annotation in Annotation.objects.filter(media_id=source_media_id):
                    forked_class = class_map.get(annotation.class_label_id)
                    if not forked_class:
                        continue
                    annotations.append(
                        Annotation(
                            media=forked_media,
                            class_label=forked_class,
                            annotator=user,
                            type=annotation.type,
                            data=annotation.data,
                            frame=annotation.frame,
                            track_id=annotation.track_id,
                            is_valid=annotation.is_valid,
                        )
                    )
            if annotations:
                Annotation.objects.bulk_create(annotations)

        return forked_project
