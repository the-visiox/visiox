from rest_framework.routers import DefaultRouter

from teams.views import TeamViewSet

router = DefaultRouter()
router.register('teams', TeamViewSet, basename='teams')

urlpatterns = router.urls
