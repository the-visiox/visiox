import hashlib
from pathlib import Path

from rest_framework import serializers

from auto_label.models import AutoLabelModel
from core.access import project_access_q
from projects.models import Project


class AutoLabelModelSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())

    class Meta:
        model = AutoLabelModel
        fields = [
            'id', 'project', 'name', 'version', 'family', 'framework',
            'task_type', 'capabilities', 'class_names', 'model_file',
            'file_size', 'checksum', 'status', 'validation_error',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'family', 'framework', 'capabilities', 'file_size',
            'checksum', 'status', 'validation_error', 'created_by',
            'created_at', 'updated_at',
        ]
        extra_kwargs = {
            'model_file': {'write_only': True},
            'name': {'required': False},
            'version': {'required': False},
            'task_type': {'required': False},
            'class_names': {'required': False},
        }

    def validate_model_file(self, model_file):
        suffix = Path(model_file.name).suffix.lower()
        if suffix != '.pt':
            raise serializers.ValidationError('Auto Label currently accepts Ultralytics .pt files only.')
        if model_file.size <= 0:
            raise serializers.ValidationError('The model file is empty.')
        return model_file

    def validate_class_names(self, value):
        if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
            raise serializers.ValidationError('class_names must be a list of non-empty strings.')
        return [item.strip() for item in value]

    def validate_project(self, project):
        user = self.context['request'].user
        if not Project.objects.filter(project_access_q(user), pk=project.pk).exists():
            raise serializers.ValidationError('You do not have access to this project.')
        return project

    def create(self, validated_data):
        model_file = validated_data['model_file']
        validated_data.setdefault('name', Path(model_file.name).stem)
        validated_data.setdefault('version', '1.0.0')
        validated_data.setdefault('task_type', 'object_detection')
        validated_data.setdefault('class_names', [])
        task_type = validated_data['task_type']
        checksum = hashlib.sha256()
        for chunk in model_file.chunks():
            checksum.update(chunk)
        model_file.seek(0)
        validated_data.update({
            'created_by': self.context['request'].user,
            'file_size': model_file.size,
            'checksum': checksum.hexdigest(),
            'capabilities': ['bbox', 'polygon'] if task_type == 'instance_segmentation' else ['bbox'],
            'status': 'ready',
        })
        return super().create(validated_data)
