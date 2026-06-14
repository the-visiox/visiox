from django.conf import settings
from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

BASE_GROUP = 'base_user'


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid='core.add_base_group')
def add_user_to_base_group(sender, instance, created, **kwargs):
    """Every user gets the base_user group on creation.

    This grants the per-user resource permissions (datasets, annotations,
    training, deployments) without requiring team membership. The group is
    created on demand; its permissions are populated by setup_groups /
    post_migrate sync.
    """
    if not created:
        return
    group, _ = Group.objects.get_or_create(name=BASE_GROUP)
    instance.groups.add(group)
