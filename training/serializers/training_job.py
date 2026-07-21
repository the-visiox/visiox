from rest_framework import serializers

from deployments.models import ModelRegistry
from training.models import TrainingJob
from training.services import training_artifact_urls
from training.validators import (
    normalize_dataset_ids,
    validate_architecture_task,
    validate_fine_tune,
    validate_hyperparams,
    validate_training_datasets,
)


COMMON_FIELDS = [
    'id', 'project', 'dataset', 'dataset_ids', 'architecture', 'architecture_name',
    'initialization_mode', 'parent_job', 'parent_job_name',
    'base_model', 'base_model_name',
    'created_by', 'created_by_username', 'name', 'status',
    'hyperparams', 'error_message', 'agent_job_id', 'artifact_urls',
    'last_heartbeat_at', 'started_at', 'finished_at', 'created_at',
    'experiment_count',
]

DETAIL_ONLY_FIELDS = [
    'class_schema', 'augmentation_config', 'artifacts', 'updated_at',
]

READ_ONLY_FIELDS = [
    'id', 'created_by', 'status', 'celery_task_id', 'error_message',
    'agent_job_id', 'artifacts', 'artifact_urls', 'last_heartbeat_at',
    'started_at', 'finished_at', 'created_at', 'updated_at', 'parent_job',
    'class_schema',
]


class TrainingJobBaseSerializer(serializers.ModelSerializer):
    architecture_name = serializers.CharField(source='architecture.name', read_only=True)
    parent_job_name = serializers.CharField(source='parent_job.name', read_only=True)
    base_model_name = serializers.CharField(source='base_model.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    experiment_count = serializers.SerializerMethodField()
    artifact_urls = serializers.SerializerMethodField()
    verify_artifact_exists = False

    def get_experiment_count(self, obj) -> int:
        annotated_count = getattr(obj, 'experiment_count_value', None)
        return annotated_count if annotated_count is not None else obj.experiments.count()

    def get_artifact_urls(self, obj) -> dict:
        return training_artifact_urls(obj, verify_exists=self.verify_artifact_exists)


class TrainingJobListSerializer(TrainingJobBaseSerializer):
    class Meta:
        model = TrainingJob
        fields = COMMON_FIELDS
        read_only_fields = READ_ONLY_FIELDS


class TrainingJobDetailSerializer(TrainingJobBaseSerializer):
    base_model = serializers.PrimaryKeyRelatedField(
        queryset=ModelRegistry.objects.select_related('training_job'),
        allow_null=True,
        required=False,
    )
    verify_artifact_exists = True

    class Meta:
        model = TrainingJob
        fields = COMMON_FIELDS + DETAIL_ONLY_FIELDS
        read_only_fields = READ_ONLY_FIELDS

    def validate_hyperparams(self, value):
        return validate_hyperparams(value)

    def validate_dataset_ids(self, value):
        return normalize_dataset_ids(value)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        project = attrs.get('project') or getattr(self.instance, 'project', None)
        dataset = attrs.get('dataset') or getattr(self.instance, 'dataset', None)
        dataset_ids = attrs.get('dataset_ids')
        if dataset_ids is None:
            dataset_ids = list(getattr(self.instance, 'dataset_ids', []) or [])
        if not dataset_ids and dataset:
            dataset_ids = [dataset.id]

        selected_datasets = validate_training_datasets(project, dataset_ids)
        if selected_datasets:
            attrs['dataset_ids'] = dataset_ids
            attrs['dataset'] = selected_datasets[0]

        architecture = attrs.get('architecture') or getattr(self.instance, 'architecture', None)
        validate_architecture_task(architecture, project)

        initialization_mode = attrs.get(
            'initialization_mode',
            getattr(self.instance, 'initialization_mode', 'architecture'),
        )
        base_model = attrs.get('base_model', getattr(self.instance, 'base_model', None))
        parent_job = validate_fine_tune(
            initialization_mode,
            base_model,
            project,
            architecture,
        )
        attrs['parent_job'] = parent_job
        if initialization_mode != 'fine_tune':
            attrs['base_model'] = None
        return attrs

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        project = validated_data['project']
        validated_data['class_schema'] = list(
            project.classes.order_by('index', 'id').values('id', 'name')
        )
        return super().create(validated_data)


# Backward-compatible import for code that previously used the single serializer.
TrainingJobSerializer = TrainingJobDetailSerializer
