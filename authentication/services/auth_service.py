from django.contrib.auth import authenticate, get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class AuthenticationService:
    @classmethod
    def _resolve_username_for_login(cls, identifier: str) -> str | None:
        """
        Django's authenticate() looks up by User.username only. Allow login with
        email when it matches a unique user (common UX; frontend often sends email
        in the 'username' field).
        """
        identifier = (identifier or "").strip()
        if not identifier:
            return None
        by_username = User.objects.filter(username__iexact=identifier).first()
        if by_username:
            return by_username.username
        by_email = User.objects.filter(email__iexact=identifier)
        if by_email.count() == 1:
            return by_email.first().username
        return identifier

    @classmethod
    def login(cls, username: str, password: str):
        resolved = cls._resolve_username_for_login(username)
        if not resolved:
            raise AuthenticationFailed("Invalid username or password.")
        user = authenticate(username=resolved, password=password)
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
