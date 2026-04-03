from django.db import models
from django.conf import settings


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
