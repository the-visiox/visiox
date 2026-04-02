import secrets

from django.conf import settings
from django.db import models


class ModelRegistry(models.Model):
    FORMAT_CHOICES = [
        ('pytorch', 'PyTorch'),
        ('onnx', 'ONNX'),
        ('tensorrt', 'TensorRT'),
        ('tflite', 'TFLite'),
        ('coreml', 'CoreML'),
    ]

    training_job = models.ForeignKey(
        'training.TrainingJob',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='registry_entries',
    )
    name = models.CharField(max_length=255)
    version = models.CharField(max_length=50, default='1.0.0')
    format = models.CharField(max_length=50, choices=FORMAT_CHOICES, default='pytorch')
    model_file = models.FileField(upload_to='models/%Y/%m/', null=True, blank=True)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    changelog = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'model_registry'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} v{self.version} ({self.format})"


class InferenceEndpoint(models.Model):
    STATUS_CHOICES = [
        ('inactive', 'Inactive'),
        ('starting', 'Starting'),
        ('active', 'Active'),
        ('stopping', 'Stopping'),
        ('error', 'Error'),
    ]

    registry_entry = models.ForeignKey(ModelRegistry, on_delete=models.CASCADE, related_name='endpoints')
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='inactive')
    endpoint_url = models.URLField(blank=True)
    auth_token = models.CharField(max_length=64, blank=True)
    rate_limit_rpm = models.PositiveIntegerField(default=100)
    confidence_threshold = models.FloatField(default=0.5)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inference_endpoints'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.auth_token:
            self.auth_token = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} [{self.status}]"


class MonitoringLog(models.Model):
    endpoint = models.ForeignKey(InferenceEndpoint, on_delete=models.CASCADE, related_name='logs')
    confidence = models.FloatField()
    prediction = models.JSONField(default=dict, blank=True)
    latency_ms = models.FloatField(null=True, blank=True)
    is_flagged = models.BooleanField(default=False)
    flagged_reason = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'monitoring_logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['endpoint', 'timestamp']),
            models.Index(fields=['is_flagged']),
        ]

    def __str__(self):
        return f"Log({self.endpoint_id}) conf={self.confidence:.2f}"


class DriftAlert(models.Model):
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    endpoint = models.ForeignKey(InferenceEndpoint, on_delete=models.CASCADE, related_name='drift_alerts')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    metric = models.CharField(max_length=100)
    threshold = models.FloatField()
    observed_value = models.FloatField()
    details = models.JSONField(default=dict, blank=True)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'drift_alerts'
        ordering = ['-created_at']

    def __str__(self):
        return f"DriftAlert({self.endpoint_id}) {self.metric}={self.observed_value:.3f}"
