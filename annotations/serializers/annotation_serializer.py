from rest_framework import serializers

from annotations.models import Annotation, Class


class AnnotationSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source='class_label.name', read_only=True)
    annotator_username = serializers.CharField(source='annotator.username', read_only=True)

    class Meta:
        model = Annotation
        fields = [
            'id', 'media', 'class_label', 'class_name',
            'annotator', 'annotator_username', 'type', 'data', 'frame', 'track_id',
            'is_valid', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'annotator', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['annotator'] = self.context['request'].user
        return super().create(validated_data)


class AnnotationWriteItemSerializer(serializers.Serializer):
    """Payload item for replacing all annotations on a job's media."""

    class_label = serializers.PrimaryKeyRelatedField(queryset=Class.objects.all())
    type = serializers.ChoiceField(choices=[c[0] for c in Annotation.ANNOTATION_TYPE_CHOICES])
    data = serializers.JSONField()
    frame = serializers.IntegerField(default=0, min_value=0)
    track_id = serializers.UUIDField(required=False, allow_null=True)


class JobAnnotationsReplaceSerializer(serializers.Serializer):
    annotations = AnnotationWriteItemSerializer(many=True)


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
