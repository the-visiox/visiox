from django.contrib import admin

from .models import Dataset, Media


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'version', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'project__name', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    list_display = ['id', 'type', 'dataset', 'original_filename', 'width', 'height', 'uploaded_at']
    list_filter = ['type', 'uploaded_at']
    search_fields = ['original_filename', 'dataset__name']
    readonly_fields = ['uploaded_at']
