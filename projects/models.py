from django.db import models
from django.conf import settings


class Project(models.Model):
    """Project model - representing a labeling project"""
    
    TASK_TYPE_CHOICES = [
        ('image_classification', 'Image Classification'),
        ('object_detection', 'Object Detection'),
        ('semantic_segmentation', 'Semantic Segmentation'),
        ('instance_segmentation', 'Instance Segmentation'),
        ('keypoint_detection', 'Keypoint Detection'),
        ('video_annotation', 'Video Annotation'),
    ]

    team = models.ForeignKey(
        'teams.Team',
        on_delete=models.CASCADE,
        related_name='projects'
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='owned_projects'
    )
    name = models.CharField(max_length=255)
    task_type = models.CharField(max_length=100, choices=TASK_TYPE_CHOICES)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'projects'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.task_type})"
