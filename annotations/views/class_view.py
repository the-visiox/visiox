from django.db import transaction
from rest_framework import viewsets

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
        ).distinct().select_related('project')

        project_id = self.request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)
        return qs

    def perform_destroy(self, instance):
        # Deleting a class cascades its annotations, but per-image label
        # profiles store the class id in JSON and would keep a stale entry.
        # Strip that id from profiles in the same project so no phantom label
        # survives the delete.
        project_id = instance.project_id
        class_id = instance.id
        with transaction.atomic():
            super().perform_destroy(instance)
            profiles = MediaLabelProfile.objects.filter(
                media__dataset__project_id=project_id,
                labels__contains=[{'id': class_id}],
            )
            for profile in profiles:
                profile.labels = [
                    label for label in (profile.labels or [])
                    if label.get('id') != class_id
                ]
                profile.save(update_fields=['labels'])
