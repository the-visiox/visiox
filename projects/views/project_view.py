from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import transaction
from django.db.models import Q

from projects.models import Project
from projects.serializers import ProjectSerializer, ProjectCreateSerializer
from projects.permissions import IsProjectOwnerOrTeamAdmin, IsProjectOwnerOrTeamOwner
from projects.filters import ProjectFilter
from teams.models import Team, TeamMember


def ensure_project_team(project):
    """Give a project its backing collaboration group (Google-Docs style).

    Every project has an implicit team: the owner is its team owner, and invited
    collaborators become team members. Creating it grants the owner the team
    permissions via the TeamMember post_save signal.
    """
    if project.team_id:
        return project.team
    team = Team.objects.create(name=project.name, owner=project.owner)
    TeamMember.objects.get_or_create(team=team, user=project.owner, defaults={'role': 'owner'})
    project.team = team
    project.save(update_fields=['team'])
    return team


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.none()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProjectFilter
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['-created_at']

    def get_permissions(self):
        # Ownership is the gate: the project owner can always edit/delete their
        # own project (object-level check), with team owner/admin as a fallback
        # when the project is shared with a team.
        if self.action in ('update', 'partial_update'):
            return [IsProjectOwnerOrTeamAdmin()]
        if self.action == 'destroy':
            return [IsProjectOwnerOrTeamOwner()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user

        return Project.objects.filter(
            Q(owner=user) | Q(team__owner=user) | Q(team__members__user=user)
        ).distinct().select_related('team').order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ProjectCreateSerializer
        return ProjectSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        project = serializer.instance
        output = ProjectSerializer(project, context={'request': request})
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)
    
    def perform_create(self, serializer):
        """Set owner and give the project its backing collaboration team."""
        with transaction.atomic():
            project = serializer.save(owner=self.request.user)
            ensure_project_team(project)
