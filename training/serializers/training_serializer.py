from rest_framework import serializers
from django.db.models import Q

from core.storage import get_artifacts_storage

from training.models import ModelArchitecture, TrainingJob, Experiment, RunMetric


KNOWN_TRAINING_ARTIFACTS = (
    'best.pt',
    'best.onnx',
    'metrics.json',
    'training_log.json',
    'confusion_matrix.png',
)


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
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class RunMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = RunMetric
        fields = [
            'id',
            'experiment',
            'epoch',
            'step',
            'loss',
            'val_loss',
            'map50',
            'map75',
            'f1',
            'accuracy',
            'extra',
            'recorded_at',
        ]
        read_only_fields = ['id', 'recorded_at']


class ExperimentSerializer(serializers.ModelSerializer):
    metrics = RunMetricSerializer(many=True, read_only=True)

    class Meta:
        model = Experiment
        fields = ['id', 'job', 'name', 'notes', 'metrics', 'created_at']
        read_only_fields = ['id', 'created_at']


class TrainingJobSerializer(serializers.ModelSerializer):
    architecture_name = serializers.CharField(source='architecture.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    experiment_count = serializers.SerializerMethodField()
    artifact_urls = serializers.SerializerMethodField()

    class Meta:
        model = TrainingJob
        fields = [
            'id', 'project', 'dataset', 'architecture', 'architecture_name',
            'created_by', 'created_by_username', 'name', 'status',
            'hyperparams', 'augmentation_config', 'error_message',
            'agent_job_id', 'artifacts', 'artifact_urls', 'last_heartbeat_at',
            'started_at', 'finished_at', 'created_at', 'updated_at',
            'experiment_count',
        ]
        read_only_fields = [
            'id',
            'created_by',
            'status',
            'celery_task_id',
            'error_message',
            'agent_job_id',
            'artifacts',
            'artifact_urls',
            'last_heartbeat_at',
            'started_at',
            'finished_at',
            'created_at',
            'updated_at',
        ]

    def validate_hyperparams(self, value):
        rules = {
            'epochs': (1, 10000, int), 'batch': (1, 1024, int),
            'batch_size': (1, 1024, int), 'imgsz': (32, 4096, int),
            'seed': (0, 2**32 - 1, int), 'device': (0, 128, int),
            'lr': (0, 1, (int, float)), 'lr0': (0, 1, (int, float)),
        }
        unknown = set(value) - set(rules)
        if unknown:
            raise serializers.ValidationError(f'Unsupported parameters: {", ".join(sorted(unknown))}')
        for key, item in value.items():
            low, high, expected = rules[key]
            if isinstance(item, bool) or not isinstance(item, expected) or not low <= item <= high:
                raise serializers.ValidationError({key: f'Must be between {low} and {high}.'})
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        project = attrs.get('project') or getattr(self.instance, 'project', None)
        dataset = attrs.get('dataset') or getattr(self.instance, 'dataset', None)
        architecture = attrs.get('architecture') or getattr(self.instance, 'architecture', None)
        if dataset and project and dataset.project_id != project.id:
            raise serializers.ValidationError({'dataset': 'Dataset must belong to the selected project.'})
        if dataset:
            raw_images = dataset.media_files.filter(type='image').filter(
                Q(metadata__category__isnull=True) | ~Q(metadata__category='augmented')
            )
            image_count = raw_images.count()
            labeled_count = raw_images.filter(
                annotations__is_valid=True,
            ).distinct().count()
            if image_count < 2:
                raise serializers.ValidationError({'dataset': 'Dataset needs at least 2 images for train/validation splits.'})
            if labeled_count == 0:
                raise serializers.ValidationError({
                    'dataset': 'Dataset needs at least 1 labeled image; remaining images may be background.'
                })
            verification_is_stale = dataset.verified_at and (
                raw_images.filter(uploaded_at__gt=dataset.verified_at).exists()
                or raw_images.filter(annotations__updated_at__gt=dataset.verified_at).exists()
            )
            if dataset.verification_status != 'verified' or not dataset.verified_at:
                raise serializers.ValidationError({'dataset': 'Verify this dataset for training first.'})
            if verification_is_stale:
                raise serializers.ValidationError({
                    'dataset': 'Dataset changed after verification. Review and verify it again.'
                })
            if project and not project.classes.exists():
                raise serializers.ValidationError({'dataset': 'Add at least 1 annotation class before training.'})
            if not dataset.split_config or not dataset.split_updated_at:
                raise serializers.ValidationError({
                    'dataset': 'Configure train, validation, and test splits before training.'
                })
            if not dataset.generation_is_current:
                raise serializers.ValidationError({
                    'dataset': 'Generate the dataset successfully before training.'
                })
        if architecture and project and architecture.task_type != project.task_type:
            raise serializers.ValidationError({
                'architecture': f'This architecture is for {architecture.task_type}, not {project.task_type}.'
            })
        return attrs

    def get_experiment_count(self, obj) -> int:
        return obj.experiments.count()

    def get_artifact_urls(self, obj) -> dict:
        storage = get_artifacts_storage()
        urls = {}
        artifacts = dict(obj.artifacts or {})
        for name in KNOWN_TRAINING_ARTIFACTS:
            artifacts.setdefault(name, {'storage_key': f'training-jobs/{obj.id}/artifacts/{name}'})
        for name, metadata in artifacts.items():
            if isinstance(metadata, dict) and metadata.get('storage_key'):
                try:
                    if not storage.exists(metadata['storage_key']):
                        continue
                    urls[name] = storage.url(metadata['storage_key'])
                except (NotImplementedError, ValueError):
                    continue
        return urls

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)
