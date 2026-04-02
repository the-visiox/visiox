from django.urls import path
from rest_framework.routers import DefaultRouter

from annotations.views import (
    ClassViewSet,
    AnnotationViewSet,
    LabelingTaskViewSet,
    ReviewViewSet,
    DatasetExportView,
    MediaQualityView,
    DatasetQualityView,
)

router = DefaultRouter()
router.register('classes', ClassViewSet, basename='classes')
router.register('annotations', AnnotationViewSet, basename='annotations')
router.register('tasks', LabelingTaskViewSet, basename='labeling-tasks')
router.register('reviews', ReviewViewSet, basename='reviews')

urlpatterns = router.urls + [
    path('datasets/<int:dataset_id>/export/', DatasetExportView.as_view(), name='dataset-export'),
    path('datasets/<int:dataset_id>/quality/', DatasetQualityView.as_view(), name='dataset-quality'),
    path('media/<int:media_id>/quality/', MediaQualityView.as_view(), name='media-quality'),
]
