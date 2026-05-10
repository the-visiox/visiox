from rest_framework.routers import DefaultRouter

from dataverse.views import DataverseProjectViewSet

router = DefaultRouter()
router.register('dataverse', DataverseProjectViewSet, basename='dataverse')

urlpatterns = router.urls
