import hashlib
import secrets

from django.conf import settings
from django.db import models


class Plan(models.Model):
    BILLING_PERIOD_CHOICES = [
        ('monthly', 'Monthly'),
        ('annual', 'Annual'),
    ]

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    price_usd = models.DecimalField(max_digits=10, decimal_places=2)
    billing_period = models.CharField(max_length=20, choices=BILLING_PERIOD_CHOICES, default='monthly')
    storage_gb = models.PositiveIntegerField(default=10)
    max_seats = models.PositiveIntegerField(default=5)
    gpu_hours_monthly = models.PositiveIntegerField(default=0)
    stripe_price_id = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'plans'
        ordering = ['price_usd']

    def __str__(self):
        return f"{self.name} (${self.price_usd}/{self.billing_period})"


class Subscription(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('past_due', 'Past Due'),
        ('cancelled', 'Cancelled'),
        ('trialing', 'Trialing'),
        ('incomplete', 'Incomplete'),
    ]

    team = models.OneToOneField('teams.Team', on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='active')
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions'

    def __str__(self):
        return f"{self.team.name} → {self.plan.name} [{self.status}]"


class UsageRecord(models.Model):
    USAGE_TYPE_CHOICES = [
        ('storage_gb', 'Storage (GB)'),
        ('gpu_hours', 'GPU Hours'),
        ('api_requests', 'API Requests'),
        ('inference_calls', 'Inference Calls'),
    ]

    team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='usage_records')
    type = models.CharField(max_length=50, choices=USAGE_TYPE_CHOICES)
    quantity = models.FloatField()
    stripe_usage_record_id = models.CharField(max_length=255, blank=True)
    billed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'usage_records'
        ordering = ['-billed_at']

    def __str__(self):
        return f"{self.team.name} | {self.type} = {self.quantity}"


class APIKey(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='api_keys')
    team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='api_keys', null=True, blank=True)
    name = models.CharField(max_length=100)
    key_hash = models.CharField(max_length=64, unique=True)
    prefix = models.CharField(max_length=8)
    is_active = models.BooleanField(default=True)
    last_used = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'api_keys'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.prefix}…)"

    @classmethod
    def generate(cls, user, name: str, team=None, expires_at=None):
        raw_key = secrets.token_hex(32)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        instance = cls.objects.create(
            user=user,
            team=team,
            name=name,
            key_hash=key_hash,
            prefix=raw_key[:8],
            expires_at=expires_at,
        )
        return instance, raw_key


class Webhook(models.Model):
    AVAILABLE_EVENTS = [
        'training.job.completed',
        'training.job.failed',
        'deployment.endpoint.started',
        'deployment.endpoint.stopped',
        'deployment.drift_alert.created',
        'billing.subscription.updated',
        'annotation.task.approved',
        'annotation.task.rejected',
    ]

    team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='webhooks')
    url = models.URLField()
    events = models.JSONField(default=list, help_text='List of subscribed event names')
    secret = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'webhooks'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.secret:
            self.secret = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.team.name} → {self.url}"
