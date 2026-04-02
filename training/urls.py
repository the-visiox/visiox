from rest_framework.routers import DefaultRouter

from training.views import ModelArchitectureViewSet, TrainingJobViewSet, ExperimentViewSet

router = DefaultRouter()
router.register('architectures', ModelArchitectureViewSet, basename='architectures')
router.register('training-jobs', TrainingJobViewSet, basename='training-jobs')
router.register('experiments', ExperimentViewSet, basename='experiments')

urlpatterns = router.urls
