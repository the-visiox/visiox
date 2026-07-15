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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'model_architectures'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.task_type})"


class TrainingJob(models.Model):
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
    architecture = models.ForeignKey(ModelArchitecture, on_delete=models.SET_NULL, null=True)
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
