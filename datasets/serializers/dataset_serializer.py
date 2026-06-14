from rest_framework import serializers

from datasets.models import Dataset, Media


class MediaSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Media
        fields = [
            'id', 'dataset', 'type', 'file', 'file_url',
            'original_filename', 'width', 'height', 'file_size',
            'metadata', 'uploaded_at',
        ]
        read_only_fields = ['id', 'file_url', 'original_filename', 'width', 'height', 'file_size', 'uploaded_at']

    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class MediaUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    type = serializers.ChoiceField(choices=['image', 'video'])
    metadata = serializers.JSONField(required=False, default=dict)


class MediaBulkDeleteSerializer(serializers.Serializer):
    media_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=500,
    )


class DatasetSerializer(serializers.ModelSerializer):
    media_count = serializers.SerializerMethodField()
    annotated_count = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Dataset
        fields = ['id', 'project', 'name', 'description', 'version', 'media_count', 'annotated_count', 'thumbnail', 'created_at', 'updated_at']
        read_only_fields = ['id', 'version', 'created_at', 'updated_at']

    def get_media_count(self, obj) -> int:
        return obj.media_files.count()

    def get_annotated_count(self, obj) -> int:
        return obj.media_files.filter(
            annotations__isnull=False,
            annotations__is_valid=True,
        ).distinct().count()

    def get_thumbnail(self, obj) -> str | None:
        first = obj.media_files.filter(type='image').order_by('uploaded_at').first()
        if not first or not first.file:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(first.file.url)
        return first.file.url
