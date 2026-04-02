from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Q

from projects.models import Project
from projects.serializers import ProjectSerializer, ProjectCreateSerializer
from projects.permissions import IsProjectOwnerOrTeamAdmin, IsProjectOwnerOrTeamOwner
from projects.filters import ProjectFilter


class ProjectViewSet(viewsets.ModelViewSet):
    
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProjectFilter
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['-created_at']
    
    def get_permissions(self):
        if self.action in ['update', 'partial_update']:
            return [IsAuthenticated(), IsProjectOwnerOrTeamAdmin()]
        elif self.action == 'destroy':
            return [IsAuthenticated(), IsProjectOwnerOrTeamOwner()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        user = self.request.user
        
        return Project.objects.filter(
            Q(team__owner=user) | Q(team__members__user=user)
        ).distinct().select_related('team').order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ProjectCreateSerializer
        return ProjectSerializer
    
    def perform_create(self, serializer):
        """Set owner when creating project"""
        serializer.save(owner=self.request.user)
