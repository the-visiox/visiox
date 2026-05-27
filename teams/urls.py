from django.urls import path
from rest_framework.routers import DefaultRouter

from teams.views import AcceptInvitationView, TeamViewSet

router = DefaultRouter()
router.register('teams', TeamViewSet, basename='teams')

urlpatterns = router.urls + [
    path('invitations/<uuid:token>/accept/', AcceptInvitationView.as_view(), name='accept-invitation'),
]
