from rest_framework import serializers

from annotations.models import Review


class ReviewSerializer(serializers.ModelSerializer):
    reviewer_username = serializers.CharField(source='reviewer.username', read_only=True)

    class Meta:
        model = Review
        fields = [
            'id', 'annotation', 'reviewer', 'reviewer_username',
            'status', 'comment', 'reviewed_at', 'updated_at',
        ]
        read_only_fields = ['id', 'reviewer', 'reviewed_at', 'updated_at']

    def create(self, validated_data):
        validated_data['reviewer'] = self.context['request'].user
        return super().create(validated_data)
