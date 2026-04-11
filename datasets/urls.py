from django.urls import path
from rest_framework.routers import DefaultRouter

from datasets.views import DatasetViewSet
from datasets.views.webhook_view import cvat_webhook

router = DefaultRouter()
router.register('datasets', DatasetViewSet, basename='datasets')

urlpatterns = [
    path('datasets/cvat-webhook/', cvat_webhook, name='cvat-webhook'),
] + router.urls
