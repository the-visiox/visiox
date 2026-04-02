from rest_framework.routers import DefaultRouter

from deployments.views import (
    ModelRegistryViewSet,
    InferenceEndpointViewSet,
    MonitoringLogViewSet,
    DriftAlertViewSet,
)

router = DefaultRouter()
router.register('registry', ModelRegistryViewSet, basename='model-registry')
router.register('endpoints', InferenceEndpointViewSet, basename='endpoints')
router.register('monitoring', MonitoringLogViewSet, basename='monitoring-logs')
router.register('drift-alerts', DriftAlertViewSet, basename='drift-alerts')

urlpatterns = router.urls
