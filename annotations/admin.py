from django.contrib import admin
from .models import Class, Annotation, LabelingTask, Review


@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'color', 'created_at']
    list_filter = ['project', 'created_at']
    search_fields = ['name', 'project__name']
    readonly_fields = ['created_at']


@admin.register(Annotation)
class AnnotationAdmin(admin.ModelAdmin):
    list_display = ['id', 'type', 'media', 'class_label', 'annotator', 'is_valid', 'created_at']
    list_filter = ['type', 'is_valid', 'created_at']
    search_fields = ['media__file_path', 'class_label__name', 'annotator__username']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(LabelingTask)
class LabelingTaskAdmin(admin.ModelAdmin):
    list_display = ['id', 'media', 'assigned_to', 'status', 'created_at', 'completed_at']
    list_filter = ['status', 'created_at']
    search_fields = ['media__file_path', 'assigned_to__username']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['id', 'annotation', 'reviewer', 'status', 'reviewed_at']
    list_filter = ['status', 'reviewed_at']
    search_fields = ['annotation__id', 'reviewer__username', 'comment']
    readonly_fields = ['reviewed_at', 'updated_at']
