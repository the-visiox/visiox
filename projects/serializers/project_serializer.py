from rest_framework import serializers
from projects.models import Project


class ProjectSerializer(serializers.ModelSerializer):
    """Serializer for Project model"""
    team_name = serializers.CharField(source='team.name', read_only=True)
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    owner_email = serializers.EmailField(source='owner.email', read_only=True)
    thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'id',
            'team',
            'team_name',
            'owner',
            'owner_username',
            'owner_email',
            'name',
            'task_type',
            'description',
            'is_public',
            'thumbnail',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'team_name', 'owner', 'owner_username', 'owner_email']

    def get_thumbnail(self, obj) -> str | None:
        from datasets.models import Media
        first = (
            Media.objects
            .filter(dataset__project=obj, type='image')
            .order_by('uploaded_at')
            .first()
        )
        if not first or not first.file:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(first.file.url)
        return first.file.url


class ProjectCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new Project.

    Projects are owned by the user who creates them; a team is optional and only
    used to share a project with other members.
    """

    class Meta:
        model = Project
        fields = [
            'team',
            'name',
            'task_type',
            'description',
            'is_public',
        ]
        extra_kwargs = {
            'team': {'required': False, 'allow_null': True},
        }

    def validate_team(self, value):
        """If a team is given, the user must own or belong to it."""
        if value is None:
            return value
        user = self.context['request'].user
        if not (value.owner == user or value.members.filter(user=user).exists()):
            raise serializers.ValidationError(
                "You don't have permission to create projects in this team."
            )
        return value
    
    def validate_name(self, value):
        """Validate project name"""
        if len(value.strip()) < 3:
            raise serializers.ValidationError(
                "Project name must be at least 3 characters long."
            )
        return value.strip()
