from django.contrib import admin

from .models import Plan, Subscription, UsageRecord, APIKey, Webhook


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'price_usd', 'billing_period', 'storage_gb', 'max_seats', 'is_active']
    list_filter = ['billing_period', 'is_active']
    search_fields = ['name']


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['team', 'plan', 'status', 'current_period_end', 'created_at']
    list_filter = ['status']
    search_fields = ['team__name', 'stripe_subscription_id']
    readonly_fields = ['stripe_customer_id', 'stripe_subscription_id', 'created_at', 'updated_at']


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ['team', 'type', 'quantity', 'billed_at']
    list_filter = ['type', 'billed_at']


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'prefix', 'team', 'is_active', 'last_used', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'user__username']
    readonly_fields = ['key_hash', 'prefix', 'last_used', 'created_at']


@admin.register(Webhook)
class WebhookAdmin(admin.ModelAdmin):
    list_display = ['team', 'url', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['team__name', 'url']
    readonly_fields = ['secret', 'created_at', 'updated_at']
