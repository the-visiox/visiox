from django.db import transaction
from django.db.models import Count, F
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from annotations.models import Class
from annotations.serializers import ClassSerializer
from core.access import project_access_q
from datasets.models import MediaLabelProfile


class ClassViewSet(viewsets.ModelViewSet):
    serializer_class = ClassSerializer
    queryset = Class.objects.none()

    def get_queryset(self):
        user = self.request.user
        qs = Class.objects.filter(
            project_access_q(user, 'project__')
        ).annotate(
            annotation_count_value=Count('annotations', distinct=True),
        ).distinct().select_related('project').order_by('index', 'id')

        project_id = self.request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)
        return qs

    @staticmethod
    def _set_order(project_id, ordered_ids):
        classes = list(
            Class.objects.select_for_update()
            .filter(project_id=project_id)
            .order_by('index', 'id')
        )
        by_id = {item.id: item for item in classes}
        if set(ordered_ids) != set(by_id) or len(ordered_ids) != len(by_id):
            return False

        # Move every row outside the final range first so the per-project
        # uniqueness constraint cannot be hit while two classes swap places.
        offset = len(classes) + max((item.index or 0) for item in classes) + 1 if classes else 1
        Class.objects.filter(project_id=project_id).update(index=F('index') + offset)
        for index, class_id in enumerate(ordered_ids):
            by_id[class_id].index = index
        Class.objects.bulk_update(classes, ['index'])
        return True

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        project_id = request.data.get('project')
        class_ids = request.data.get('class_ids')
        if not isinstance(project_id, int) or not isinstance(class_ids, list):
            return Response(
                {'detail': 'project and class_ids are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if any(not isinstance(class_id, int) for class_id in class_ids):
            return Response(
                {'detail': 'class_ids must contain integer class IDs.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        accessible_ids = list(
            self.get_queryset()
            .filter(project_id=project_id)
            .values_list('id', flat=True)
        )
        if not accessible_ids:
            return Response({'detail': 'Project classes not found.'}, status=status.HTTP_404_NOT_FOUND)
        if set(class_ids) != set(accessible_ids) or len(class_ids) != len(accessible_ids):
            return Response(
                {'detail': 'class_ids must include every class in the project exactly once.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            if not self._set_order(project_id, class_ids):
                return Response(
                    {'detail': 'Class order changed. Reload and try again.'},
                    status=status.HTTP_409_CONFLICT,
                )

        reordered = self.get_queryset().filter(project_id=project_id)
        return Response(self.get_serializer(reordered, many=True).data)

    def perform_destroy(self, instance):
        # Deleting a class cascades its annotations, but per-image label
        # profiles store the class id in JSON and would keep a stale entry.
        # Strip that id from profiles in the same project so no phantom label
        # survives the delete.
        project_id = instance.project_id
        class_id = instance.id
        with transaction.atomic():
            super().perform_destroy(instance)
            remaining_ids = list(
                Class.objects.filter(project_id=project_id)
                .order_by('index', 'id')
                .values_list('id', flat=True)
            )
            self._set_order(project_id, remaining_ids)
            profiles = list(MediaLabelProfile.objects.filter(
                media__dataset__project_id=project_id,
                labels__contains=[{'id': class_id}],
            ).only('id', 'labels'))
            for profile in profiles:
                profile.labels = [
                    label for label in (profile.labels or [])
                    if label.get('id') != class_id
                ]
            if profiles:
                MediaLabelProfile.objects.bulk_update(
                    profiles,
                    ['labels'],
                    batch_size=500,
                )
