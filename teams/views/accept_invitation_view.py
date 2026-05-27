from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from teams.models import Invitation, TeamMember
from teams.serializers import TeamMemberSerializer


class AcceptInvitationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, token):
        try:
            invitation = Invitation.objects.select_related('team').get(token=token)
        except Invitation.DoesNotExist:
            return Response({'error': 'Invalid invitation link.'}, status=status.HTTP_404_NOT_FOUND)

        if invitation.status == Invitation.STATUS_ACCEPTED:
            return Response({'error': 'This invitation has already been accepted.'}, status=status.HTTP_400_BAD_REQUEST)

        if invitation.status == Invitation.STATUS_CANCELLED:
            return Response({'error': 'This invitation has been cancelled.'}, status=status.HTTP_400_BAD_REQUEST)

        if invitation.status == Invitation.STATUS_EXPIRED or timezone.now() > invitation.expires_at:
            invitation.status = Invitation.STATUS_EXPIRED
            invitation.save()
            return Response({'error': 'This invitation has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        if TeamMember.objects.filter(team=invitation.team, user=request.user).exists():
            invitation.status = Invitation.STATUS_ACCEPTED
            invitation.save()
            return Response({'detail': 'You are already a member of this team.'}, status=status.HTTP_200_OK)

        member = TeamMember.objects.create(
            team=invitation.team,
            user=request.user,
            role=invitation.role,
        )
        invitation.status = Invitation.STATUS_ACCEPTED
        invitation.save()

        return Response(
            {'detail': f'You have joined {invitation.team.name}!', 'member': TeamMemberSerializer(member).data},
            status=status.HTTP_200_OK,
        )
