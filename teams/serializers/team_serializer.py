from django.contrib.auth import get_user_model
from rest_framework import serializers

from teams.models import Invitation, Team, TeamMember

User = get_user_model()


class TeamMemberSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = TeamMember
        fields = ['id', 'user', 'user_username', 'user_email', 'role', 'joined_at']
        read_only_fields = ['id', 'joined_at']


class TeamSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = ['id', 'name', 'owner', 'owner_username', 'member_count', 'created_at']
        read_only_fields = ['id', 'owner', 'created_at']

    def get_member_count(self, obj) -> int:
        return obj.members.count()

    def create(self, validated_data):
        user = self.context['request'].user
        team = Team.objects.create(owner=user, **validated_data)
        TeamMember.objects.create(team=team, user=user, role='owner')
        return team


class InviteMemberSerializer(serializers.Serializer):
    username = serializers.CharField()
    role = serializers.ChoiceField(choices=['admin', 'member', 'viewer'], default='member')

    def validate_username(self, value):
        try:
            return User.objects.get(username=value)
        except User.DoesNotExist:
            raise serializers.ValidationError(f"User '{value}' not found.")


class UpdateMemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=['admin', 'member', 'viewer'])


class SendInvitationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=['admin', 'member', 'viewer'], default='member')


class InvitationSerializer(serializers.ModelSerializer):
    invited_by_username = serializers.CharField(source='invited_by.username', read_only=True)

    class Meta:
        model = Invitation
        fields = ['id', 'email', 'role', 'status', 'invited_by_username', 'created_at', 'expires_at']
        read_only_fields = fields
