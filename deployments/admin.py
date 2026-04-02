from django.contrib import admin

from .models import ModelRegistry, InferenceEndpoint, MonitoringLog, DriftAlert


@admin.register(ModelRegistry)
class ModelRegistryAdmin(admin.ModelAdmin):
    list_display = ['name', 'version', 'format', 'training_job', 'created_by', 'created_at']
    list_filter = ['format', 'created_at']
    search_fields = ['name', 'version']
    readonly_fields = ['file_size', 'created_at', 'updated_at']


@admin.register(InferenceEndpoint)
class InferenceEndpointAdmin(admin.ModelAdmin):
    list_display = ['name', 'registry_entry', 'status', 'rate_limit_rpm', 'created_at']
    list_filter = ['status']
    search_fields = ['name']
    readonly_fields = ['auth_token', 'created_at', 'updated_at']


@admin.register(MonitoringLog)
class MonitoringLogAdmin(admin.ModelAdmin):
    list_display = ['endpoint', 'confidence', 'is_flagged', 'timestamp']
    list_filter = ['is_flagged', 'timestamp']
    readonly_fields = ['timestamp']


@admin.register(DriftAlert)
class DriftAlertAdmin(admin.ModelAdmin):
    list_display = ['endpoint', 'severity', 'metric', 'observed_value', 'is_resolved', 'created_at']
    list_filter = ['severity', 'is_resolved']
    readonly_fields = ['created_at', 'resolved_at']
