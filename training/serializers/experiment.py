from rest_framework import serializers

from training.models import Experiment
from training.serializers.metric import RunMetricSerializer


class ExperimentSerializer(serializers.ModelSerializer):
    metrics = RunMetricSerializer(many=True, read_only=True)

    class Meta:
        model = Experiment
        fields = ['id', 'job', 'name', 'notes', 'metrics', 'created_at']
        read_only_fields = ['id', 'created_at']
