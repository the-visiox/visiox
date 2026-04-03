from django.contrib.auth.models import Group
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from teams.models import TeamMember

ROLE_PRIORITY = ['owner', 'admin', 'member', 'viewer']
ALL_ROLE_GROUPS = {f'role_{r}' for r in ROLE_PRIORITY}


def _sync_user_groups(user) -> None:
    """Sync user's role_* Group membership to their highest TeamMember role."""
    roles = list(TeamMember.objects.filter(user=user).values_list('role', flat=True))
    highest = next((r for r in ROLE_PRIORITY if r in roles), None)

    target_groups = set()
    if highest:
        target_groups = {f'role_{highest}'}

    current_role_groups = set(
        user.groups.filter(name__in=ALL_ROLE_GROUPS).values_list('name', flat=True)
    )

    to_add = target_groups - current_role_groups
    to_remove = current_role_groups - target_groups

    if to_add:
        groups_to_add = Group.objects.filter(name__in=to_add)
        user.groups.add(*groups_to_add)

    if to_remove:
        groups_to_remove = Group.objects.filter(name__in=to_remove)
        user.groups.remove(*groups_to_remove)


@receiver(post_save, sender=TeamMember)
def on_team_member_save(sender, instance, **kwargs):
    _sync_user_groups(instance.user)


@receiver(post_delete, sender=TeamMember)
def on_team_member_delete(sender, instance, **kwargs):
    _sync_user_groups(instance.user)
