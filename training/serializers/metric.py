from rest_framework import serializers

from training.models import RunMetric


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
