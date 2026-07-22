from rest_framework import serializers

from core.storage import get_artifacts_storage
from deployments.models import ModelRegistry, InferenceEndpoint, MonitoringLog, DriftAlert


class ModelRegistrySerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    endpoint_count = serializers.SerializerMethodField()
    artifact_url = serializers.SerializerMethodField()

    class Meta:
        model = ModelRegistry
        fields = [
            'id', 'training_job', 'name', 'version', 'format',
            'model_file', 'file_size', 'metrics', 'changelog',
            'artifact_url', 'created_by', 'created_by_username', 'endpoint_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'file_size', 'created_at', 'updated_at']

    def get_endpoint_count(self, obj) -> int:
        annotated_count = getattr(obj, 'endpoint_count_value', None)
        return annotated_count if annotated_count is not None else obj.endpoints.count()

    def get_artifact_url(self, obj) -> str | None:
        if not obj.model_file:
            return None
        try:
            return get_artifacts_storage().url(obj.model_file.name)
        except (NotImplementedError, ValueError):
            return None

    def create(self, validated_data):
        model_file = validated_data.get('model_file')
        if model_file:
            validated_data['file_size'] = model_file.size
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class InferenceEndpointSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = InferenceEndpoint
        fields = [
            'id', 'registry_entry', 'name', 'status', 'endpoint_url',
            'auth_token', 'rate_limit_rpm', 'confidence_threshold',
            'created_by', 'created_by_username', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'status', 'auth_token', 'created_by', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class MonitoringLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonitoringLog
        fields = [
            'id',
            'endpoint',
            'confidence',
            'prediction',
            'latency_ms',
            'is_flagged',
            'flagged_reason',
            'timestamp',
        ]
        read_only_fields = ['id', 'is_flagged', 'flagged_reason', 'timestamp']


class DriftAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriftAlert
        fields = [
            'id',
            'endpoint',
            'severity',
            'metric',
            'threshold',
            'observed_value',
            'details',
            'is_resolved',
            'created_at',
            'resolved_at',
        ]
        read_only_fields = ['id', 'created_at', 'resolved_at']
