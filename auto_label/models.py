import uuid
from pathlib import Path

from django.conf import settings
from django.db import models

from core.storage import get_artifacts_storage


def auto_label_model_upload_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f'auto-label/projects/{instance.project_id}/models/{uuid.uuid4().hex}{suffix}'


class AutoLabelModel(models.Model):
    TASK_CHOICES = [
        ('object_detection', 'Object Detection'),
        ('instance_segmentation', 'Instance Segmentation'),
    ]
    STATUS_CHOICES = [
        ('validating', 'Validating'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]

    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='auto_label_models')
    name = models.CharField(max_length=255)
    version = models.CharField(max_length=50, default='1.0.0')
    family = models.CharField(max_length=100, default='yolo')
    framework = models.CharField(max_length=100, default='ultralytics')
    task_type = models.CharField(max_length=50, choices=TASK_CHOICES)
    capabilities = models.JSONField(default=list)
    class_names = models.JSONField(default=list, blank=True)
    model_file = models.FileField(upload_to=auto_label_model_upload_path, storage=get_artifacts_storage)
    file_size = models.PositiveBigIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='validating')
    validation_error = models.TextField(blank=True)
    is_temporary = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'auto_label_models'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} v{self.version} ({self.task_type})'

    def delete(self, *args, **kwargs):
        storage = self.model_file.storage
        name = self.model_file.name
        result = super().delete(*args, **kwargs)
        if name:
            storage.delete(name)
        return result


class AutoLabelDatasetJob(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('error', 'Error'),
    ]

    dataset = models.ForeignKey('datasets.Dataset', on_delete=models.CASCADE, related_name='auto_label_jobs')
    model = models.ForeignKey(AutoLabelModel, on_delete=models.CASCADE, related_name='dataset_jobs')
    output_type = models.CharField(max_length=20, default='bbox')
    confidence = models.FloatField(default=0.45)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    total = models.PositiveIntegerField(default=0)
    done = models.PositiveIntegerField(default=0)
    labeled_images = models.PositiveIntegerField(default=0)
    saved_annotations = models.PositiveIntegerField(default=0)
    skipped_predictions = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'auto_label_dataset_jobs'
        ordering = ['-created_at']

    def __str__(self):
        return f'AutoLabelDatasetJob {self.id} ({self.status}) {self.done}/{self.total}'
