from rest_framework import serializers

from annotations.models import Class


class ClassSerializer(serializers.ModelSerializer):
    annotation_count = serializers.SerializerMethodField()

    class Meta:
        model = Class
        fields = ['id', 'project', 'index', 'name', 'color', 'attributes', 'annotation_count', 'created_at']
        read_only_fields = ['id', 'index', 'created_at']

    def get_annotation_count(self, obj) -> int:
        annotated_count = getattr(obj, 'annotation_count_value', None)
        return annotated_count if annotated_count is not None else obj.annotations.count()
