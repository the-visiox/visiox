from django.contrib import admin
from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'team', 'task_type', 'created_at']
    list_filter = ['task_type', 'created_at']
    search_fields = ['name', 'team__name', 'description']
    readonly_fields = ['created_at', 'updated_at']
