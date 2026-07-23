import hashlib
import tempfile
from pathlib import Path

from rest_framework import serializers

from auto_label.models import AutoLabelModel
from core.access import project_access_q
from projects.models import Project


def inspect_ultralytics_model(model_file):
    checksum = hashlib.sha256()
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.pt', delete=False) as temporary:
            temporary_path = Path(temporary.name)
            for chunk in model_file.chunks():
                checksum.update(chunk)
                temporary.write(chunk)
        model_file.seek(0)
        try:
            from ultralytics import YOLO
            model = YOLO(str(temporary_path))
        except Exception as exc:
            raise serializers.ValidationError({
                'model_file': f'Could not read this Ultralytics model: {exc}',
            }) from exc
        task = str(model.task or '').lower()
        if task not in ('detect', 'segment'):
            raise serializers.ValidationError({
                'model_file': f'Unsupported Ultralytics task "{task or "unknown"}". Use detect or segment.',
            })
        raw_names = model.names or {}
        if isinstance(raw_names, dict):
            class_names = [str(raw_names[index]) for index in sorted(raw_names, key=lambda value: int(value))]
        else:
            class_names = [str(name) for name in raw_names]
        if not class_names:
            raise serializers.ValidationError({'model_file': 'The model does not declare any class names.'})
        return {
            'checksum': checksum.hexdigest(),
            'task_type': 'instance_segmentation' if task == 'segment' else 'object_detection',
            'capabilities': ['bbox', 'polygon'] if task == 'segment' else ['bbox'],
            'class_names': class_names,
        }
    finally:
        model_file.seek(0)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


class AutoLabelModelSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())

    class Meta:
        model = AutoLabelModel
        fields = [
            'id', 'project', 'name', 'version', 'family', 'framework',
            'task_type', 'capabilities', 'class_names', 'model_file',
            'file_size', 'checksum', 'status', 'validation_error', 'is_temporary',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'family', 'framework', 'capabilities', 'file_size',
            'checksum', 'status', 'validation_error', 'is_temporary', 'created_by',
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
        metadata = inspect_ultralytics_model(model_file)
        validated_data['task_type'] = metadata['task_type']
        validated_data['class_names'] = metadata['class_names']
        validated_data.update({
            'created_by': self.context['request'].user,
            'file_size': model_file.size,
            'checksum': metadata['checksum'],
            'capabilities': metadata['capabilities'],
            'status': 'ready',
            'is_temporary': True,
        })
        return super().create(validated_data)
