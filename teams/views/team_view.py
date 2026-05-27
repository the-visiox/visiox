from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.permissions import HasPerm
from teams.email_service import send_invitation_email
from teams.models import Invitation, Team, TeamMember
from teams.permissions import IsTeamOwnerOrAdmin
from teams.serializers import (
    InvitationSerializer,
    InviteMemberSerializer,
    SendInvitationSerializer,
    TeamMemberSerializer,
    TeamSerializer,
    UpdateMemberRoleSerializer,
)


class TeamViewSet(viewsets.ModelViewSet):
    serializer_class = TeamSerializer
    queryset = Team.objects.none()

    def get_queryset(self):
        user = self.request.user
        return Team.objects.filter(members__user=user).distinct()

    def get_permissions(self):
        if self.action == 'destroy':
            return [HasPerm('teams.delete_team'), IsTeamOwnerOrAdmin()]
        if self.action in ('update', 'partial_update'):
            return [HasPerm('teams.update_member_role'), IsTeamOwnerOrAdmin()]
        if self.action in ('invite', 'remove_member', 'update_member_role',
                           'send_invitation', 'list_invitations', 'cancel_invitation'):
            return [HasPerm('teams.invite_member'), IsTeamOwnerOrAdmin()]
        return super().get_permissions()

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        team = self.get_object()
        members = team.members.select_related('user').all()
        serializer = TeamMemberSerializer(members, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def invite(self, request, pk=None):
        team = self.get_object()
        self.check_object_permissions(request, team)
        serializer = InviteMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['username']
        role = serializer.validated_data['role']

        if TeamMember.objects.filter(team=team, user=user).exists():
            return Response({'error': 'User is already a member.'}, status=status.HTTP_400_BAD_REQUEST)

        member = TeamMember.objects.create(team=team, user=user, role=role)
        return Response(TeamMemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path=r'members/(?P<member_id>\d+)')
    def remove_member(self, request, pk=None, member_id=None):
        team = self.get_object()
        self.check_object_permissions(request, team)
        try:
            member = TeamMember.objects.get(pk=member_id, team=team)
        except TeamMember.DoesNotExist:
            return Response({'error': 'Member not found.'}, status=status.HTTP_404_NOT_FOUND)

        if member.role == 'owner':
            return Response({'error': 'Cannot remove the team owner.'}, status=status.HTTP_400_BAD_REQUEST)

        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['patch'], url_path=r'members/(?P<member_id>\d+)/role')
    def update_member_role(self, request, pk=None, member_id=None):
        team = self.get_object()
        self.check_object_permissions(request, team)
        try:
            member = TeamMember.objects.get(pk=member_id, team=team)
        except TeamMember.DoesNotExist:
            return Response({'error': 'Member not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = UpdateMemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member.role = serializer.validated_data['role']
        member.save()
        return Response(TeamMemberSerializer(member).data)

    # ── Email invitations ────────────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='send_invitation')
    def send_invitation(self, request, pk=None):
        team = self.get_object()
        self.check_object_permissions(request, team)
        serializer = SendInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        role = serializer.validated_data['role']

        # Cancel any previous pending invite for this email
        Invitation.objects.filter(team=team, email=email, status=Invitation.STATUS_PENDING).update(
            status=Invitation.STATUS_CANCELLED
        )

        invitation = Invitation.objects.create(
            team=team,
            email=email,
            role=role,
            invited_by=request.user,
        )

        try:
            send_invitation_email(invitation)
        except Exception:
            invitation.delete()
            return Response({'error': 'Failed to send invitation email.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='invitations')
    def list_invitations(self, request, pk=None):
        team = self.get_object()
        invitations = team.invitations.exclude(status=Invitation.STATUS_CANCELLED)
        # Auto-expire stale pending ones
        now = timezone.now()
        stale = invitations.filter(status=Invitation.STATUS_PENDING, expires_at__lt=now)
        stale.update(status=Invitation.STATUS_EXPIRED)
        return Response(InvitationSerializer(invitations, many=True).data)

    @action(detail=True, methods=['delete'], url_path=r'invitations/(?P<invite_id>\d+)')
    def cancel_invitation(self, request, pk=None, invite_id=None):
        team = self.get_object()
        self.check_object_permissions(request, team)
        try:
            invitation = Invitation.objects.get(pk=invite_id, team=team)
        except Invitation.DoesNotExist:
            return Response({'error': 'Invitation not found.'}, status=status.HTTP_404_NOT_FOUND)
        invitation.status = Invitation.STATUS_CANCELLED
        invitation.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
