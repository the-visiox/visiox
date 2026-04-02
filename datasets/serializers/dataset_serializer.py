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


class DatasetSerializer(serializers.ModelSerializer):
    media_count = serializers.SerializerMethodField()

    class Meta:
        model = Dataset
        fields = ['id', 'project', 'name', 'description', 'version', 'media_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'version', 'created_at', 'updated_at']

    def get_media_count(self, obj) -> int:
        return obj.media_files.count()
