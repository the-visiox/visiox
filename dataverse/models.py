from django.conf import settings
from django.db import models


class DataverseProject(models.Model):
    """Public listing for a project shared into the VisioX Dataverse."""

    source_project = models.OneToOneField(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='dataverse_listing',
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='dataverse_projects',
    )
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True)
    tags = models.JSONField(default=list, blank=True)
    license = models.CharField(max_length=100, default='Community')
    is_public = models.BooleanField(default=True)
    fork_count = models.PositiveIntegerField(default=0)
    view_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'dataverse_projects'
        ordering = ['-updated_at']

    def __str__(self):
        return self.title

