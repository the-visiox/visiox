from rest_framework.permissions import BasePermission


class HasPerm(BasePermission):
    """
    Gate 1: checks that the authenticated user holds a specific Django permission
    (granted via role_* Group membership). Pair with an object-level permission
    class as Gate 2 for full two-gate authorization.

    Usage:
        permission_classes = [HasPerm('datasets.upload_media'), IsProjectOwnerOrTeamAdmin]
    """

    def __init__(self, perm: str) -> None:
        self.perm = perm

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.has_perm(self.perm))
