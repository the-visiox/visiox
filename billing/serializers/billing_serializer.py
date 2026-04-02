from rest_framework import serializers

from billing.models import Plan, Subscription, UsageRecord, APIKey, Webhook


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            'id', 'name', 'description', 'price_usd', 'billing_period',
            'storage_gb', 'max_seats', 'gpu_hours_monthly', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    team_name = serializers.CharField(source='team.name', read_only=True)

    class Meta:
        model = Subscription
        fields = [
            'id', 'team', 'team_name', 'plan', 'plan_name', 'status',
            'current_period_start', 'current_period_end', 'cancelled_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'team_name', 'plan_name', 'status',
            'stripe_customer_id', 'stripe_subscription_id',
            'current_period_start', 'current_period_end',
            'cancelled_at', 'created_at', 'updated_at',
        ]


class CreateSubscriptionSerializer(serializers.Serializer):
    team_id = serializers.IntegerField()
    plan_id = serializers.IntegerField()


class UsageRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageRecord
        fields = ['id', 'team', 'type', 'quantity', 'billed_at']
        read_only_fields = ['id', 'billed_at']


class APIKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = ['id', 'name', 'prefix', 'team', 'is_active', 'last_used', 'expires_at', 'created_at']
        read_only_fields = ['id', 'prefix', 'last_used', 'created_at']


class CreateAPIKeySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    team_id = serializers.IntegerField(required=False)
    expires_at = serializers.DateTimeField(required=False)


class WebhookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Webhook
        fields = ['id', 'team', 'url', 'events', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
