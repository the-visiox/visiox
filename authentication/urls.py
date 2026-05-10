from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from authentication.views import LoginView, RegisterView, LogoutView, MeView, OAuthLoginView

urlpatterns = [
    path('login/', LoginView.as_view(), name='auth-login'),
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('oauth/', OAuthLoginView.as_view(), name='auth-oauth'),
    path('token/refresh/', TokenRefreshView.as_view(), name='auth-token-refresh'),
]
