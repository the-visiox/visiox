from django.urls import path
from rest_framework.routers import DefaultRouter

from auto_label.views import (
    AutoLabelModelViewSet,
    AutoLabelProviderListView,
    DatasetAutoLabelJobView,
    DatasetAutoLabelView,
    FrameAutoLabelPredictView,
)

router = DefaultRouter()
router.register('auto-label/models', AutoLabelModelViewSet, basename='auto-label-models')

urlpatterns = [
    path('auto-label/providers/', AutoLabelProviderListView.as_view(), name='auto-label-providers'),
    path('datasets/<int:dataset_id>/auto-label/', DatasetAutoLabelView.as_view(), name='auto-label-dataset'),
    path(
        'datasets/<int:dataset_id>/auto-label/jobs/<int:job_id>/',
        DatasetAutoLabelJobView.as_view(),
        name='auto-label-dataset-job',
    ),
    path(
        'datasets/<int:dataset_id>/frames/<int:frame_num>/predict/',
        FrameAutoLabelPredictView.as_view(),
        name='auto-label-frame-predict',
    ),
    *router.urls,
]
