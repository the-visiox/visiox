from django.conf import settings
from django.db import models


class ModelArchitecture(models.Model):
    TASK_TYPES = [
        ('object_detection', 'Object Detection'),
        ('image_classification', 'Image Classification'),
        ('semantic_segmentation', 'Semantic Segmentation'),
        ('instance_segmentation', 'Instance Segmentation'),
        ('keypoint_detection', 'Keypoint Detection'),
    ]

    name = models.CharField(max_length=255)
    backbone = models.CharField(max_length=255, blank=True)
    task_type = models.CharField(max_length=100, choices=TASK_TYPES)
    description = models.TextField(blank=True)
    default_config = models.JSONField(default=dict, blank=True)
    is_builtin = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'model_architectures'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.task_type})"


class TrainingJob(models.Model):
    INITIALIZATION_CHOICES = [
        ('architecture', 'Architecture checkpoint'),
        ('fine_tune', 'Fine-tune from registered model'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='training_jobs')
    dataset = models.ForeignKey('datasets.Dataset', on_delete=models.SET_NULL, null=True, related_name='training_jobs')
    dataset_ids = models.JSONField(default=list, blank=True)
    architecture = models.ForeignKey(ModelArchitecture, on_delete=models.SET_NULL, null=True)
    parent_job = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='child_jobs'
    )
    base_model = models.ForeignKey(
        'deployments.ModelRegistry', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fine_tuning_jobs',
    )
    initialization_mode = models.CharField(
        max_length=32, choices=INITIALIZATION_CHOICES, default='architecture'
    )
    class_schema = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    hyperparams = models.JSONField(default=dict, blank=True)
    augmentation_config = models.JSONField(default=dict, blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True)
    agent_job_id = models.CharField(max_length=255, blank=True)
    artifacts = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'training_jobs'
        ordering = ['-created_at']
        permissions = [
            ('start_job', 'Can start a training job'),
            ('stop_job', 'Can stop a training job'),
        ]

    def __str__(self):
        return f"{self.name} [{self.status}]"

    def selected_datasets(self):
        from datasets.models import Dataset

        ids = list(dict.fromkeys(self.dataset_ids or ([self.dataset_id] if self.dataset_id else [])))
        rows = {item.id: item for item in Dataset.objects.filter(id__in=ids).select_related('project')}
        return [rows[dataset_id] for dataset_id in ids if dataset_id in rows]


class Experiment(models.Model):
    job = models.ForeignKey(TrainingJob, on_delete=models.CASCADE, related_name='experiments')
    name = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'experiments'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} (job={self.job_id})"


class RunMetric(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, related_name='metrics')
    epoch = models.PositiveIntegerField()
    step = models.PositiveIntegerField(default=0)
    loss = models.FloatField(null=True, blank=True)
    val_loss = models.FloatField(null=True, blank=True)
    map50 = models.FloatField(null=True, blank=True)
    map75 = models.FloatField(null=True, blank=True)
    f1 = models.FloatField(null=True, blank=True)
    accuracy = models.FloatField(null=True, blank=True)
    extra = models.JSONField(default=dict, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'run_metrics'
        ordering = ['epoch', 'step']

    def __str__(self):
        return f"Epoch {self.epoch} | loss={self.loss}"
