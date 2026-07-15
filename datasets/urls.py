from django.urls import path
from rest_framework.routers import DefaultRouter

from datasets.views import DatasetViewSet, MediaMetadataView

router = DefaultRouter()
router.register('datasets', DatasetViewSet, basename='datasets')

urlpatterns = [
    path('media/<int:media_id>/', MediaMetadataView.as_view(), name='media-metadata'),
    *router.urls,
]
