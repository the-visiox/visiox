from rest_framework import serializers

from dataverse.models import DataverseProject
from projects.models import Project
from teams.models import Team


class DataverseProjectSerializer(serializers.ModelSerializer):
    source_project = serializers.IntegerField(source='source_project_id', read_only=True)
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    team_name = serializers.CharField(source='source_project.team.name', read_only=True)
    task_type = serializers.CharField(source='source_project.task_type', read_only=True)
    dataset_count = serializers.SerializerMethodField()
    media_count = serializers.SerializerMethodField()
    class_count = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = DataverseProject
        fields = [
            'id',
            'source_project',
            'owner',
            'owner_username',
            'team_name',
            'title',
            'summary',
            'tags',
            'license',
            'is_public',
            'task_type',
            'dataset_count',
            'media_count',
            'class_count',
            'thumbnail',
            'fork_count',
            'view_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_dataset_count(self, obj) -> int:
        return obj.source_project.datasets.count()

    def get_media_count(self, obj) -> int:
        return sum(ds.media_files.count() for ds in obj.source_project.datasets.all())

    def get_class_count(self, obj) -> int:
        return obj.source_project.classes.count()

    def get_thumbnail(self, obj) -> str | None:
        first = (
            obj.source_project.datasets
            .filter(media_files__type='image')
            .order_by('media_files__uploaded_at')
            .values_list('media_files__file', flat=True)
            .first()
        )
        if not first:
            return None
        request = self.context.get('request')
        url = f'/media/{first}'
        if request:
            return request.build_absolute_uri(url)
        return url


class DataverseShareSerializer(serializers.Serializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    summary = serializers.CharField(required=False, allow_blank=True)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        allow_empty=True,
    )
    license = serializers.CharField(max_length=100, required=False, allow_blank=True)
    is_public = serializers.BooleanField(required=False, default=True)

    def validate_project(self, project):
        user = self.context['request'].user
        if project.owner_id == user.id or project.team.owner_id == user.id:
            return project
        if project.team.members.filter(user=user, role__in=['owner', 'admin']).exists():
            return project
        raise serializers.ValidationError("You need owner or admin access to share this project.")


class DataverseForkSerializer(serializers.Serializer):
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all())
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_team(self, team):
        user = self.context['request'].user
        if team.owner_id == user.id or team.members.filter(user=user).exists():
            return team
        raise serializers.ValidationError("You do not have access to this team.")

