import re

from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver


def _slug(name: str) -> str:
    """'Factory Floor v2' -> 'factory-floor-v2' (max 40 chars)"""
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:40]


def media_upload_path(instance, filename):
    """
    users/{owner_id}_{owner_slug}/projects/{project_id}_{project_slug}/
        datasets/{dataset_id}_{dataset_slug}/v{version}/{category}/{filename}

    Storage is keyed by the project owner (the user who created it), not the team.
    Team membership only grants access — it never changes where files live.

    Set instance._upload_category = 'augmented' before saving augmented images.
    """
    category = getattr(instance, '_upload_category', 'raw')
    project = instance.dataset.project
    dataset = instance.dataset
    owner = project.owner

    owner_folder   = f"{owner.id}_{_slug(owner.username)}" if owner else "0_unknown"
    project_folder = f"{project.id}_{_slug(project.name)}"
    dataset_folder = f"{dataset.id}_{_slug(dataset.name)}"

    return (
        f"users/{owner_folder}/projects/{project_folder}/"
        f"datasets/{dataset_folder}/v{dataset.version}/{category}/{filename}"
    )


def media_thumb_path(instance, filename):
    """Store the thumbnail next to its original under a `thumbs/` subfolder, so it
    inherits the same owner/project/dataset/category path. Derived from the saved
    original path (reliable) rather than the upload category flag."""
    base = instance.file.name if instance.file else ''
    if base and '/' in base:
        head, tail = base.rsplit('/', 1)
        stem = tail.rsplit('.', 1)[0]
        return f"{head}/thumbs/{stem}.jpg"
    return f"thumbs/{filename}"


class Dataset(models.Model):
    VERIFICATION_CHOICES = [
        ('unverified', 'Unverified'),
        ('verified', 'Verified for training'),
    ]
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='datasets'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    version = models.PositiveIntegerField(default=1)
    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_CHOICES,
        default='unverified',
    )
    verified_by = models.ForeignKey(
        'core.UserModel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_datasets',
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    split_config = models.JSONField(default=dict, blank=True)
    split_updated_at = models.DateTimeField(null=True, blank=True)
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

    def invalidate_training_verification(self):
        """Require review and a fresh split after raw annotations change."""
        if (
            self.verification_status == 'unverified'
            and not self.verified_at
            and not self.verified_by_id
            and not self.split_config
            and not self.split_updated_at
        ):
            return
        self.verification_status = 'unverified'
        self.verified_by = None
        self.verified_at = None
        self.split_config = {}
        self.split_updated_at = None
        self.save(update_fields=[
            'verification_status', 'verified_by', 'verified_at',
            'split_config', 'split_updated_at', 'updated_at',
        ])

        raw_media = []
        for media in self.media_files.filter(type='image').only('id', 'metadata'):
            metadata = dict(media.metadata or {})
            if metadata.get('category') == 'augmented' or 'split' not in metadata:
                continue
            metadata.pop('split', None)
            media.metadata = metadata
            raw_media.append(media)
        if raw_media:
            Media.objects.bulk_update(raw_media, ['metadata'])

    @property
    def generation_is_current(self):
        """Whether the current verified split has been generated successfully."""
        if not self.verified_at or not self.split_updated_at:
            return False
        if (self.split_config or {}).get('source') in ('imported_yolo26', 'imported_coco'):
            return True
        generated_after = max(self.verified_at, self.split_updated_at)
        return self.augmentation_jobs.filter(
            status='done',
            updated_at__gte=generated_after,
        ).exists()


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
    file = models.FileField(upload_to=media_upload_path, max_length=500)
    # Precomputed gallery thumbnail (built once, then served from storage / CDN).
    thumbnail = models.FileField(upload_to=media_thumb_path, max_length=500, null=True, blank=True)
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


@receiver(post_delete, sender=Media)
def delete_media_storage_files(sender, instance, **kwargs):
    """Remove files from storage when a media row is deleted.

    Django deletes database rows on cascade, but FileField contents are not
    removed automatically. Keep the original and generated thumbnail in sync
    with the database lifecycle.
    """
    if instance.file:
        instance.file.delete(save=False)
    if instance.thumbnail:
        instance.thumbnail.delete(save=False)


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


class AugmentationJob(models.Model):
    """Tracks a dataset-augmentation run so progress is shared across all web
    workers and survives process restarts (instead of an in-memory dict)."""

    STATUS_CHOICES = [
        ('running', 'Running'),
        ('done', 'Done'),
        ('error', 'Error'),
    ]

    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name='augmentation_jobs',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    total = models.PositiveIntegerField(default=0)
    done = models.PositiveIntegerField(default=0)
    generated = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'augmentation_jobs'
        ordering = ['-created_at']

    def __str__(self):
        return f"AugmentationJob {self.id} ({self.status}) {self.done}/{self.total}"


class DatasetImportJob(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('error', 'Error'),
    ]
    FORMAT_CHOICES = [
        ('images', 'Images'),
        ('yolo26', 'YOLO26'),
        ('coco', 'COCO'),
    ]

    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name='import_jobs',
    )
    format = models.CharField(max_length=20, choices=FORMAT_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    staged_files = models.JSONField(default=list, blank=True)
    total = models.PositiveIntegerField(default=0)
    done = models.PositiveIntegerField(default=0)
    summary = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        'core.UserModel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dataset_import_jobs',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'dataset_import_jobs'
        ordering = ['-created_at']

    def __str__(self):
        return f"DatasetImportJob {self.id} ({self.format}/{self.status}) {self.done}/{self.total}"
