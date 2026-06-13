from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sync_role_groups_after_migrate(sender, **kwargs):
    """Ensure role_* Groups exist with correct permissions after every migrate.

    Connected without a sender filter so it runs once per migrated app; the call
    is idempotent and self-healing, so by the time the last app is processed all
    permissions exist and every group is fully populated.
    """
    from core.management.commands.setup_groups import sync_role_groups
    sync_role_groups()


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        post_migrate.connect(
            _sync_role_groups_after_migrate,
            dispatch_uid='core.sync_role_groups',
        )
        # Register the post_save handler that puts new users in base_user.
        from core import signals  # noqa: F401
