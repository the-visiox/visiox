from rest_framework import serializers

from training.models import ModelArchitecture, TrainingJob, Experiment, RunMetric


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

    class Meta:
        model = TrainingJob
        fields = [
            'id', 'project', 'dataset', 'architecture', 'architecture_name',
            'created_by', 'created_by_username', 'name', 'status',
            'hyperparams', 'augmentation_config', 'error_message',
            'started_at', 'finished_at', 'created_at', 'updated_at',
            'experiment_count',
        ]
        read_only_fields = [
            'id',
            'created_by',
            'status',
            'celery_task_id',
            'error_message',
            'started_at',
            'finished_at',
            'created_at',
            'updated_at',
        ]

    def get_experiment_count(self, obj) -> int:
        return obj.experiments.count()

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)
