from django.contrib.auth import authenticate, get_user_model
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class AuthenticationService:
    @classmethod
    def login(cls, username: str, password: str):
        user = authenticate(username=username, password=password)
        if not user:
            raise AuthenticationFailed("Invalid username or password.")

        access_token, refresh_token = cls.generate_token(user)
        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'user_id': user.pk,
        }

    @classmethod
    def sign_up(cls, username: str, email: str, password: str, first_name: str = '', last_name: str = ''):
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        access_token, refresh_token = cls.generate_token(user)
        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'user_id': user.pk,
        }

    @classmethod
    def generate_token(cls, user) -> tuple[str, str]:
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token), str(refresh)
