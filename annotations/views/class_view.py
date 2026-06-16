from rest_framework import viewsets

from annotations.models import Class
from annotations.serializers import ClassSerializer
from core.access import project_access_q


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
