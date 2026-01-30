from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import exceptions 

class AuthenticationService:
    @classmethod
    def login(cls, username: str, password: str):
        user = authenticate(username=username, password=password)
        if not user:
            raise exceptions.AuthenticationFailed()
        
        access_token, refresh_token = cls.generate_token(user)
        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'user_id': user.pk
        }
    
    @classmethod
    def sign_up(cls, user_info):
        pass
    
    @classmethod
    def generate_token(cls, user) -> tuple[str, str]:
        refresh = RefreshToken.for_user(user)
        
        return (
            str(refresh.access_token), str(refresh)
        )
        