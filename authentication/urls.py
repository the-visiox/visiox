from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from authentication.views import LoginView, RegisterView, LogoutView, MeView

urlpatterns = [
    path('login/', LoginView.as_view(), name='auth-login'),
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('token/refresh/', TokenRefreshView.as_view(), name='auth-token-refresh'),
]
