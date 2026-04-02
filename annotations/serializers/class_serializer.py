from rest_framework import serializers

from annotations.models import Class


class ClassSerializer(serializers.ModelSerializer):
    annotation_count = serializers.SerializerMethodField()

    class Meta:
        model = Class
        fields = ['id', 'project', 'name', 'color', 'attributes', 'annotation_count', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_annotation_count(self, obj) -> int:
        return obj.annotations.count()
