import uuid
from datetime import timedelta

from django.db import models
from django.conf import settings
from django.utils import timezone


class Team(models.Model):
    """Team model - representing a group of users working together"""
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_teams'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'teams'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class TeamMember(models.Model):
    """TeamMember model - representing membership of users in teams"""
    
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('member', 'Member'),
        ('viewer', 'Viewer'),
    ]

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='members'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='team_memberships'
    )
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'team_members'
        unique_together = ['team', 'user']
        ordering = ['-joined_at']
        permissions = [
            ('invite_member', 'Can invite team members'),
            ('remove_member', 'Can remove team members'),
            ('update_member_role', 'Can update member roles'),
            ('delete_team', 'Can delete a team'),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.team.name} ({self.role})"


class Invitation(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_EXPIRED = 'expired'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_EXPIRED, 'Expired'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('member', 'Member'),
        ('viewer', 'Viewer'),
    ]

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='member')
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_invitations',
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'team_invitations'
        ordering = ['-created_at']
        unique_together = ['team', 'email', 'status']

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"Invitation to {self.email} for {self.team.name}"
