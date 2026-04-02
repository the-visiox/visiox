from rest_framework import serializers

from annotations.models import LabelingTask


class LabelingTaskSerializer(serializers.ModelSerializer):
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True)
    media_url = serializers.SerializerMethodField()

    class Meta:
        model = LabelingTask
        fields = [
            'id', 'media', 'media_url', 'assigned_to', 'assigned_to_username',
            'status', 'created_at', 'updated_at', 'completed_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'completed_at']

    def get_media_url(self, obj) -> str | None:
        request = self.context.get('request')
        if obj.media.file and request:
            return request.build_absolute_uri(obj.media.file.url)
        return None
