from django_filters import rest_framework as filters
from projects.models import Project


class ProjectFilter(filters.FilterSet):
    """Filter for Project model"""
    
    # Filter by owner
    owner = filters.NumberFilter(field_name='owner__id')
    owned_by_me = filters.BooleanFilter(method='filter_owned_by_me')
    
    # Filter by team
    team = filters.NumberFilter(field_name='team__id')
    team_owner = filters.BooleanFilter(method='filter_team_owner')
    
    # Filter by task type
    task_type = filters.ChoiceFilter(choices=Project.TASK_TYPE_CHOICES)
    
    # Search by name
    name = filters.CharFilter(lookup_expr='icontains')
    
    class Meta:
        model = Project
        fields = ['owner', 'team', 'task_type', 'name']
    
    def filter_owned_by_me(self, queryset, name, value):
        """Filter projects owned by current user"""
        if value:
            return queryset.filter(owner=self.request.user)
        return queryset
    
    def filter_team_owner(self, queryset, name, value):
        """Filter projects where user is team owner"""
        if value:
            return queryset.filter(team__owner=self.request.user)
        return queryset
