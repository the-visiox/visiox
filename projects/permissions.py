from rest_framework import permissions


class IsProjectOwnerOrTeamAdmin(permissions.BasePermission):
    """
    Permission: Allow project owner, team owner, or team admin to update
    """
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return True
        
        user = request.user
        
        # Check if user is project owner
        if obj.owner == user:
            return True
        
        # Check if user is team owner
        if obj.team.owner == user:
            return True
        
        # Check if user is team admin
        if obj.team.members.filter(user=user, role__in=['owner', 'admin']).exists():
            return True
        
        return False


class IsProjectOwnerOrTeamOwner(permissions.BasePermission):
    """
    Permission: Only project owner or team owner can delete
    """
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return True
        
        user = request.user
        
        # Only project owner or team owner can delete
        return obj.owner == user or obj.team.owner == user
