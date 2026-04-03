from rest_framework.permissions import BasePermission

from teams.models import TeamMember


def get_member_role(team, user):
    try:
        return TeamMember.objects.get(team=team, user=user).role
    except TeamMember.DoesNotExist:
        return None


class IsTeamOwnerOrAdmin(BasePermission):
    """Allow only team owner or admin members."""

    def has_object_permission(self, request, view, obj):
        role = get_member_role(obj, request.user)
        return role in ('owner', 'admin')


