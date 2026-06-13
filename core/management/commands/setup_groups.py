from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand


ROLE_PERMISSION_MAP = {
    'role_owner': [
        # Team management
        'teams.delete_team',
        'teams.invite_member',
        'teams.remove_member',
        'teams.update_member_role',
        # Projects
        'projects.add_project',
        'projects.change_project',
        'projects.delete_project',
        'projects.view_project',
        # Datasets
        'datasets.add_dataset',
        'datasets.change_dataset',
        'datasets.delete_dataset',
        'datasets.view_dataset',
        'datasets.upload_media',
        'datasets.export_dataset',
        # Annotations
        'annotations.add_annotation',
        'annotations.change_annotation',
        'annotations.delete_annotation',
        'annotations.view_annotation',
        'annotations.review_annotation',
        'annotations.approve_annotation',
        # Training
        'training.add_trainingjob',
        'training.change_trainingjob',
        'training.view_trainingjob',
        'training.start_job',
        'training.stop_job',
        # Deployments
        'deployments.add_inferenceendpoint',
        'deployments.change_inferenceendpoint',
        'deployments.view_inferenceendpoint',
        'deployments.start_endpoint',
        'deployments.stop_endpoint',
    ],
    'role_admin': [
        # Team management (no delete_team)
        'teams.invite_member',
        'teams.remove_member',
        'teams.update_member_role',
        # Projects (no delete_project)
        'projects.add_project',
        'projects.change_project',
        'projects.view_project',
        # Datasets
        'datasets.add_dataset',
        'datasets.change_dataset',
        'datasets.delete_dataset',
        'datasets.view_dataset',
        'datasets.upload_media',
        'datasets.export_dataset',
        # Annotations
        'annotations.add_annotation',
        'annotations.change_annotation',
        'annotations.delete_annotation',
        'annotations.view_annotation',
        'annotations.review_annotation',
        'annotations.approve_annotation',
        # Training
        'training.add_trainingjob',
        'training.change_trainingjob',
        'training.view_trainingjob',
        'training.start_job',
        'training.stop_job',
        # Deployments
        'deployments.add_inferenceendpoint',
        'deployments.change_inferenceendpoint',
        'deployments.view_inferenceendpoint',
        'deployments.start_endpoint',
        'deployments.stop_endpoint',
    ],
    'role_member': [
        # Projects
        'projects.add_project',
        'projects.view_project',
        # Datasets
        'datasets.add_dataset',
        'datasets.change_dataset',
        'datasets.view_dataset',
        'datasets.upload_media',
        'datasets.export_dataset',
        # Annotations
        'annotations.add_annotation',
        'annotations.change_annotation',
        'annotations.view_annotation',
        # Training
        'training.add_trainingjob',
        'training.view_trainingjob',
        'training.start_job',
        'training.stop_job',
        # Deployments (view only)
        'deployments.view_inferenceendpoint',
    ],
    'role_viewer': [
        # Read-only access
        'projects.view_project',
        'datasets.view_dataset',
        'annotations.view_annotation',
        'training.view_trainingjob',
        'deployments.view_inferenceendpoint',
    ],
    # Base permissions granted to EVERY user (assigned on signup, not via a team).
    # Projects are gated by ownership at the object level, so they need no model
    # permission here; this group covers the per-user resources a solo user owns.
    'base_user': [
        # Datasets
        'datasets.add_dataset',
        'datasets.change_dataset',
        'datasets.delete_dataset',
        'datasets.view_dataset',
        'datasets.upload_media',
        'datasets.export_dataset',
        # Annotations
        'annotations.add_annotation',
        'annotations.change_annotation',
        'annotations.delete_annotation',
        'annotations.view_annotation',
        'annotations.review_annotation',
        'annotations.approve_annotation',
        # Training
        'training.add_trainingjob',
        'training.change_trainingjob',
        'training.view_trainingjob',
        'training.start_job',
        'training.stop_job',
        # Deployments
        'deployments.add_inferenceendpoint',
        'deployments.change_inferenceendpoint',
        'deployments.view_inferenceendpoint',
        'deployments.start_endpoint',
        'deployments.stop_endpoint',
    ],
}


def _get_permission(app_label: str, codename: str) -> Permission | None:
    return Permission.objects.filter(
        content_type__app_label=app_label, codename=codename
    ).first()


def sync_role_groups() -> list[dict]:
    """Create the role_* Groups and assign their permissions (idempotent).

    Safe to call repeatedly. Permissions not yet created (e.g. when invoked from
    post_migrate before every app has been processed) are simply skipped; a later
    call fills them in. Returns a per-group summary for callers that want to log.
    """
    summary = []
    for group_name, dotted_perms in ROLE_PERMISSION_MAP.items():
        group, created = Group.objects.get_or_create(name=group_name)

        perms = []
        missing = []
        for dotted in dotted_perms:
            app_label, codename = dotted.split('.', 1)
            perm = _get_permission(app_label, codename)
            if perm:
                perms.append(perm)
            else:
                missing.append(dotted)

        group.permissions.set(perms)
        summary.append({
            'group': group_name,
            'created': created,
            'count': len(perms),
            'missing': missing,
        })
    return summary


class Command(BaseCommand):
    help = 'Create role_* Groups and assign the correct permissions (idempotent).'

    def handle(self, *args, **options):
        for row in sync_role_groups():
            action = 'Created' if row['created'] else 'Updated'
            self.stdout.write(
                self.style.SUCCESS(f'{action} group "{row["group"]}" with {row["count"]} permission(s).')
            )
            for m in row['missing']:
                self.stdout.write(self.style.WARNING(f'  Permission not found (run migrate first): {m}'))
