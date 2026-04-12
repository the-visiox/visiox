from rest_framework import serializers

from annotations.models import JobIssue


class JobIssueSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source='author.username', read_only=True)

    class Meta:
        model = JobIssue
        fields = ['id', 'task', 'author', 'author_username', 'body', 'created_at']
        read_only_fields = ['id', 'task', 'author', 'created_at']

    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user
        validated_data['task'] = self.context['task']
        return super().create(validated_data)
