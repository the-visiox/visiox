from django.db import models


class Dataset(models.Model):
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='datasets'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    version = models.PositiveIntegerField(default=1)
    cvat_task_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'datasets'
        ordering = ['-created_at']
        permissions = [
            ('upload_media', 'Can upload media to a dataset'),
            ('export_dataset', 'Can export a dataset'),
        ]

    def __str__(self):
        return f"{self.name} v{self.version} - {self.project.name}"


class Media(models.Model):
    MEDIA_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
    ]

    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name='media_files'
    )
    type = models.CharField(max_length=50, choices=MEDIA_TYPE_CHOICES)
    file = models.FileField(upload_to='media/%Y/%m/%d/')
    original_filename = models.CharField(max_length=255, blank=True)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'media'
        ordering = ['-uploaded_at']
        verbose_name_plural = 'Media'

    def __str__(self):
        return f"{self.type} - {self.original_filename or self.file.name}"


class MediaLabelProfile(models.Model):
    """Per-image label roster (name/color) stored in Postgres.

    IDs in ``labels`` should match ``annotations.Class`` PKs for the owning project
    so existing annotation payloads keep working.
    """

    media = models.OneToOneField(
        Media,
        on_delete=models.CASCADE,
        related_name='label_profile',
    )
    labels = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'media_label_profiles'

    def __str__(self):
        return f"Label profile for media {self.media_id}"
