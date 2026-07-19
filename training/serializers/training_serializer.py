from rest_framework import serializers
from django.db.models import Q

from core.storage import get_artifacts_storage
from datasets.models import Dataset

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
    parent_job_name = serializers.CharField(source='parent_job.name', read_only=True)
    base_model_name = serializers.CharField(source='base_model.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    experiment_count = serializers.SerializerMethodField()
    artifact_urls = serializers.SerializerMethodField()

    class Meta:
        model = TrainingJob
        fields = [
            'id', 'project', 'dataset', 'dataset_ids', 'architecture', 'architecture_name',
            'initialization_mode', 'parent_job', 'parent_job_name',
            'base_model', 'base_model_name', 'class_schema',
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
            'parent_job',
            'class_schema',
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

    def validate_dataset_ids(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('Must be a list of dataset ids.')
        if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value):
            raise serializers.ValidationError('Every dataset id must be a positive integer.')
        return list(dict.fromkeys(value))

    def validate(self, attrs):
        attrs = super().validate(attrs)
        project = attrs.get('project') or getattr(self.instance, 'project', None)
        dataset = attrs.get('dataset') or getattr(self.instance, 'dataset', None)
        dataset_ids = attrs.get('dataset_ids')
        if dataset_ids is None:
            dataset_ids = list(getattr(self.instance, 'dataset_ids', []) or [])
        if not dataset_ids and dataset:
            dataset_ids = [dataset.id]
        selected_datasets = list(Dataset.objects.filter(id__in=dataset_ids).select_related('project'))
        selected_by_id = {item.id: item for item in selected_datasets}
        if len(selected_by_id) != len(dataset_ids):
            raise serializers.ValidationError({'dataset_ids': 'One or more selected datasets do not exist.'})
        selected_datasets = [selected_by_id[dataset_id] for dataset_id in dataset_ids]
        if selected_datasets:
            attrs['dataset_ids'] = dataset_ids
            attrs['dataset'] = selected_datasets[0]
        architecture = attrs.get('architecture') or getattr(self.instance, 'architecture', None)
        if project and any(item.project_id != project.id for item in selected_datasets):
            raise serializers.ValidationError({'dataset_ids': 'Every dataset must belong to the selected project.'})
        for dataset in selected_datasets:
            raw_images = dataset.media_files.filter(type='image').filter(
                Q(metadata__category__isnull=True) | ~Q(metadata__category='augmented')
            )
            image_count = raw_images.count()
            labeled_count = raw_images.filter(
                annotations__is_valid=True,
            ).distinct().count()
            if image_count < 2:
                raise serializers.ValidationError({
                    'dataset_ids': f'{dataset.name} needs at least 2 images for train/validation splits.'
                })
            if labeled_count == 0:
                raise serializers.ValidationError({
                    'dataset_ids': f'{dataset.name} needs at least 1 labeled image; remaining images may be background.'
                })
            verification_is_stale = dataset.verified_at and (
                raw_images.filter(uploaded_at__gt=dataset.verified_at).exists()
                or raw_images.filter(annotations__updated_at__gt=dataset.verified_at).exists()
            )
            if dataset.verification_status != 'verified' or not dataset.verified_at:
                raise serializers.ValidationError({'dataset_ids': f'Verify {dataset.name} for training first.'})
            if verification_is_stale:
                raise serializers.ValidationError({
                    'dataset_ids': f'{dataset.name} changed after verification. Review and verify it again.'
                })
            if project and not project.classes.exists():
                raise serializers.ValidationError({'dataset': 'Add at least 1 annotation class before training.'})
            if not dataset.split_config or not dataset.split_updated_at:
                raise serializers.ValidationError({
                    'dataset_ids': f'Configure train, validation, and test splits for {dataset.name}.'
                })
            if not dataset.generation_is_current:
                raise serializers.ValidationError({
                    'dataset_ids': f'Generate {dataset.name} successfully before training.'
                })
        if architecture and project and architecture.task_type != project.task_type:
            raise serializers.ValidationError({
                'architecture': f'This architecture is for {architecture.task_type}, not {project.task_type}.'
            })

        initialization_mode = attrs.get(
            'initialization_mode',
            getattr(self.instance, 'initialization_mode', 'architecture'),
        )
        base_model = attrs.get('base_model', getattr(self.instance, 'base_model', None))
        if initialization_mode == 'fine_tune':
            if base_model is None:
                raise serializers.ValidationError({
                    'base_model': 'Select a completed PyTorch model to fine-tune from.'
                })
            parent_job = base_model.training_job
            if base_model.format != 'pytorch' or not base_model.model_file:
                raise serializers.ValidationError({
                    'base_model': 'Fine-tuning currently requires a registered PyTorch .pt model.'
                })
            if parent_job is None or parent_job.status != 'completed':
                raise serializers.ValidationError({
                    'base_model': 'The source model must belong to a completed training run.'
                })
            if project and parent_job.project_id != project.id:
                raise serializers.ValidationError({
                    'base_model': 'The source model must belong to the selected project.'
                })
            if architecture and parent_job.architecture_id != architecture.id:
                raise serializers.ValidationError({
                    'architecture': 'Use the same architecture as the source training run.'
                })
            current_schema = list(project.classes.order_by('id').values('id', 'name')) if project else []
            parent_names = [item.get('name') for item in (parent_job.class_schema or [])]
            current_names = [item['name'] for item in current_schema]
            if parent_names and parent_names != current_names:
                raise serializers.ValidationError({
                    'base_model': 'Project classes changed after the source run. Restore the original class order before fine-tuning.'
                })
            attrs['parent_job'] = parent_job
        else:
            attrs['base_model'] = None
            attrs['parent_job'] = None
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
        project = validated_data['project']
        validated_data['class_schema'] = list(project.classes.order_by('id').values('id', 'name'))
        return super().create(validated_data)
