from django.contrib import admin

from .models import ModelArchitecture, TrainingJob, Experiment, RunMetric


@admin.register(ModelArchitecture)
class ModelArchitectureAdmin(admin.ModelAdmin):
    list_display = ['name', 'backbone', 'task_type', 'is_builtin', 'created_at']
    list_filter = ['task_type', 'is_builtin']
    search_fields = ['name', 'backbone']


@admin.register(TrainingJob)
class TrainingJobAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'status', 'architecture', 'created_by', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'project__name']
    readonly_fields = ['celery_task_id', 'started_at', 'finished_at', 'created_at', 'updated_at']


@admin.register(Experiment)
class ExperimentAdmin(admin.ModelAdmin):
    list_display = ['name', 'job', 'created_at']


@admin.register(RunMetric)
class RunMetricAdmin(admin.ModelAdmin):
    list_display = ['experiment', 'epoch', 'loss', 'map50', 'f1', 'recorded_at']
