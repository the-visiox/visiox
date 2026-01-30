from django.urls import re_path
from authentication.views import LoginView


urlpatterns = [
    re_path(
        'login', LoginView.as_view(), name='login-view'
    )
]
