from django.urls import path
from rest_framework.routers import DefaultRouter

from billing.views import (
    PlanViewSet,
    SubscriptionViewSet,
    UsageViewSet,
    APIKeyViewSet,
    WebhookViewSet,
    StripeWebhookView,
)

router = DefaultRouter()
router.register('plans', PlanViewSet, basename='plans')
router.register('subscriptions', SubscriptionViewSet, basename='subscriptions')
router.register('usage', UsageViewSet, basename='usage')
router.register('api-keys', APIKeyViewSet, basename='api-keys')
router.register('webhooks', WebhookViewSet, basename='webhooks')

urlpatterns = router.urls + [
    path('webhooks/stripe/', StripeWebhookView.as_view(), name='stripe-webhook'),
]
