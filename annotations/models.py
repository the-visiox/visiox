from django.db import models
from django.conf import settings


class Class(models.Model):
    """Class model - representing annotation classes/categories"""
    
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='classes'
    )
    name = models.CharField(max_length=255)
    color = models.CharField(max_length=7, default='#000000')  # Hex color code
    attributes = models.JSONField(default=dict, blank=True)  # Custom attributes for the class
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'classes'
        verbose_name_plural = 'Classes'
        unique_together = ['project', 'name']
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - {self.project.name}"


class Annotation(models.Model):
    """Annotation model - representing individual annotations on media"""
    
    ANNOTATION_TYPE_CHOICES = [
        ('bbox', 'Bounding Box'),
        ('rectangle', 'Rectangle'),
        ('polygon', 'Polygon'),
        ('polyline', 'Polyline'),
        ('point', 'Point'),
        ('keypoint', 'Keypoint'),
        ('mask', 'Mask'),
        ('cuboid', 'Cuboid'),
        ('tag', 'Tag'),
    ]

    media = models.ForeignKey(
        'datasets.Media',
        on_delete=models.CASCADE,
        related_name='annotations'
    )
    class_label = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name='annotations'
    )
    annotator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='annotations'
    )
    type = models.CharField(max_length=50, choices=ANNOTATION_TYPE_CHOICES)
    data = models.JSONField()  # Stores annotation coordinates and shape data
    frame = models.PositiveIntegerField(
        default=0,
        help_text='Frame index for video; 0 for single images.',
    )
    track_id = models.UUIDField(
        null=True,
        blank=True,
        help_text='Optional stable id for video object tracks across frames.',
    )
    is_valid = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'annotations'
        ordering = ['-created_at']
        permissions = [
            ('review_annotation', 'Can review annotations'),
            ('approve_annotation', 'Can approve annotations'),
        ]

    def __str__(self):
        return f"{self.type} - {self.class_label.name} on {self.media.id}"


class JobIssue(models.Model):
    """Review / QA comment attached to a labeling job (task)."""

    task = models.ForeignKey(
        'LabelingTask',
        on_delete=models.CASCADE,
        related_name='issues',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='job_issues',
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'job_issues'
        ordering = ['-created_at']

    def __str__(self):
        return f"Issue on task {self.task_id}"


class LabelingTask(models.Model):
    """LabelingTask model - representing tasks assigned to annotators"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    media = models.ForeignKey(
        'datasets.Media',
        on_delete=models.CASCADE,
        related_name='labeling_tasks'
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks'
    )
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'labeling_tasks'
        ordering = ['-created_at']

    def __str__(self):
        assignee = self.assigned_to.username if self.assigned_to else 'Unassigned'
        return f"Task {self.id} - {assignee} - {self.status}"


class Review(models.Model):
    """Review model - representing reviews of annotations"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('needs_revision', 'Needs Revision'),
    ]

    annotation = models.ForeignKey(
        Annotation,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='reviews_given'
    )
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    comment = models.TextField(blank=True, null=True)
    reviewed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reviews'
        ordering = ['-reviewed_at']

    def __str__(self):
        reviewer_name = self.reviewer.username if self.reviewer else 'Unknown'
        return f"Review by {reviewer_name} - {self.status}"
