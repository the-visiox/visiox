from drf_spectacular.utils import extend_schema
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from billing.models import Plan, Subscription, UsageRecord, APIKey, Webhook
from billing.serializers import (
    PlanSerializer,
    SubscriptionSerializer,
    CreateSubscriptionSerializer,
    UsageRecordSerializer,
    APIKeySerializer,
    CreateAPIKeySerializer,
    WebhookSerializer,
)
from billing.services import StripeService


class PlanViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PlanSerializer
    queryset = Plan.objects.filter(is_active=True)
    permission_classes = [IsAuthenticated]


class SubscriptionViewSet(viewsets.GenericViewSet):
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Subscription.objects.filter(
            team__members__user=self.request.user
        ).distinct()

    @extend_schema(request=CreateSubscriptionSerializer, responses={201: SubscriptionSerializer})
    @action(detail=False, methods=['post'])
    def subscribe(self, request):
        serializer = CreateSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from teams.models import Team
        try:
            team = Team.objects.get(pk=serializer.validated_data['team_id'], members__user=request.user)
            plan = Plan.objects.get(pk=serializer.validated_data['plan_id'], is_active=True)
        except (Team.DoesNotExist, Plan.DoesNotExist) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sub = StripeService.create_subscription(team, plan, request.user.email)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(SubscriptionSerializer(sub).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses={200: SubscriptionSerializer})
    @action(detail=False, methods=['get'])
    def my_subscription(self, request):
        team_id = request.query_params.get('team_id')
        qs = self.get_queryset()
        if team_id:
            qs = qs.filter(team_id=team_id)
        sub = qs.first()
        if not sub:
            return Response({'detail': 'No subscription found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(SubscriptionSerializer(sub).data)

    @extend_schema(responses={204: None})
    @action(detail=False, methods=['post'])
    def cancel(self, request):
        team_id = request.data.get('team_id')
        try:
            sub = Subscription.objects.get(team_id=team_id, team__members__user=request.user)
        except Subscription.DoesNotExist:
            return Response({'error': 'Subscription not found.'}, status=status.HTTP_404_NOT_FOUND)

        StripeService.cancel_subscription(sub)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UsageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UsageRecordSerializer
    permission_classes = [IsAuthenticated]
    queryset = UsageRecord.objects.none()

    def get_queryset(self):
        return UsageRecord.objects.filter(
            team__members__user=self.request.user
        ).distinct()


class APIKeyViewSet(viewsets.GenericViewSet):
    serializer_class = APIKeySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return APIKey.objects.filter(user=self.request.user, is_active=True)

    @extend_schema(responses={200: APIKeySerializer(many=True)})
    def list(self, request):
        serializer = APIKeySerializer(self.get_queryset(), many=True)
        return Response(serializer.data)

    @extend_schema(request=CreateAPIKeySerializer, responses={201: dict})
    def create(self, request):
        serializer = CreateAPIKeySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        team = None
        team_id = serializer.validated_data.get('team_id')
        if team_id:
            from teams.models import Team
            try:
                team = Team.objects.get(pk=team_id, members__user=request.user)
            except Team.DoesNotExist:
                return Response({'error': 'Team not found.'}, status=status.HTTP_400_BAD_REQUEST)

        instance, raw_key = APIKey.generate(
            user=request.user,
            name=serializer.validated_data['name'],
            team=team,
            expires_at=serializer.validated_data.get('expires_at'),
        )

        data = APIKeySerializer(instance).data
        data['key'] = raw_key
        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(responses={204: None})
    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        try:
            key = APIKey.objects.get(pk=pk, user=request.user)
        except APIKey.DoesNotExist:
            return Response({'error': 'API key not found.'}, status=status.HTTP_404_NOT_FOUND)
        key.is_active = False
        key.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class WebhookViewSet(viewsets.ModelViewSet):
    serializer_class = WebhookSerializer
    permission_classes = [IsAuthenticated]
    queryset = Webhook.objects.none()

    def get_queryset(self):
        return Webhook.objects.filter(
            team__members__user=self.request.user
        ).distinct()

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        from deployments.tasks import deliver_webhook
        webhook = self.get_object()
        task = deliver_webhook.delay(webhook.id, 'test.ping', {'message': 'Webhook test'})
        return Response({'task_id': task.id, 'message': 'Test webhook queued.'})
