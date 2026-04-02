from rest_framework import serializers

from annotations.models import Annotation


class AnnotationSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source='class_label.name', read_only=True)
    annotator_username = serializers.CharField(source='annotator.username', read_only=True)

    class Meta:
        model = Annotation
        fields = [
            'id', 'media', 'class_label', 'class_name',
            'annotator', 'annotator_username', 'type', 'data',
            'is_valid', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'annotator', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['annotator'] = self.context['request'].user
        return super().create(validated_data)


class BulkAnnotationSerializer(serializers.Serializer):
    annotations = AnnotationSerializer(many=True)

    def create(self, validated_data):
        user = self.context['request'].user
        items = validated_data['annotations']
        objects = [
            Annotation(annotator=user, **item)
            for item in items
        ]
        return Annotation.objects.bulk_create(objects)
