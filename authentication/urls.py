from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from authentication.throttles import TokenRefreshRateThrottle
from authentication.views import LoginView, RegisterView, LogoutView, MeView, OAuthLoginView


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_classes = [TokenRefreshRateThrottle]


urlpatterns = [
    path('login/', LoginView.as_view(), name='auth-login'),
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('oauth/', OAuthLoginView.as_view(), name='auth-oauth'),
    path('token/refresh/', ThrottledTokenRefreshView.as_view(), name='auth-token-refresh'),
]
