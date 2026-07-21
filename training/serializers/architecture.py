from rest_framework import serializers

from training.models import ModelArchitecture


class ModelArchitectureSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelArchitecture
        fields = [
            'id',
            'name',
            'backbone',
            'task_type',
            'description',
            'default_config',
            'is_builtin',
            'is_active',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']
