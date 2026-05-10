import secrets
from typing import Any

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed, ValidationError

from authentication.services.auth_service import AuthenticationService

User = get_user_model()


def _configured(value: str) -> bool:
    return bool(value and not value.startswith('PASTE_'))


class OAuthService:
    GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
    GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v3/userinfo'
    GITHUB_TOKEN_URL = 'https://github.com/login/oauth/access_token'
    GITHUB_USER_URL = 'https://api.github.com/user'
    GITHUB_EMAILS_URL = 'https://api.github.com/user/emails'

    @classmethod
    def login(cls, provider: str, code: str, redirect_uri: str) -> dict[str, Any]:
        if provider == 'google':
            profile = cls._google_profile(code, redirect_uri)
        elif provider == 'github':
            profile = cls._github_profile(code, redirect_uri)
        else:
            raise ValidationError({'provider': 'Unsupported OAuth provider.'})

        email = (profile.get('email') or '').strip().lower()
        if not email:
            raise AuthenticationFailed('OAuth provider did not return an email address.')

        user = cls._get_or_create_user(
            email=email,
            name=profile.get('name') or '',
            username_hint=profile.get('username') or email.split('@')[0],
        )
        access_token, refresh_token = AuthenticationService.generate_token(user)
        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'user_id': user.pk,
        }

    @classmethod
    def _google_profile(cls, code: str, redirect_uri: str) -> dict[str, str]:
        client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '')
        client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '')
        if not _configured(client_id) or not _configured(client_secret):
            raise ValidationError({'provider': 'Google OAuth is not configured.'})

        token_data = cls._post_json(
            cls.GOOGLE_TOKEN_URL,
            {
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code,
                'grant_type': 'authorization_code',
                'redirect_uri': redirect_uri,
            },
        )
        access_token = token_data.get('access_token')
        if not access_token:
            raise AuthenticationFailed('Google did not return an access token.')

        userinfo = cls._get_json(
            cls.GOOGLE_USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'},
        )
        if userinfo.get('email_verified') is False:
            raise AuthenticationFailed('Google email address is not verified.')
        return {
            'email': userinfo.get('email', ''),
            'name': userinfo.get('name', ''),
            'username': userinfo.get('email', '').split('@')[0],
        }

    @classmethod
    def _github_profile(cls, code: str, redirect_uri: str) -> dict[str, str]:
        client_id = getattr(settings, 'GITHUB_OAUTH_CLIENT_ID', '')
        client_secret = getattr(settings, 'GITHUB_OAUTH_CLIENT_SECRET', '')
        if not _configured(client_id) or not _configured(client_secret):
            raise ValidationError({'provider': 'GitHub OAuth is not configured.'})

        token_data = cls._post_json(
            cls.GITHUB_TOKEN_URL,
            {
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code,
                'redirect_uri': redirect_uri,
            },
            headers={'Accept': 'application/json'},
        )
        access_token = token_data.get('access_token')
        if not access_token:
            raise AuthenticationFailed('GitHub did not return an access token.')

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/vnd.github+json',
        }
        userinfo = cls._get_json(cls.GITHUB_USER_URL, headers=headers)
        email = userinfo.get('email') or cls._github_primary_email(headers)
        return {
            'email': email or '',
            'name': userinfo.get('name') or userinfo.get('login') or '',
            'username': userinfo.get('login') or '',
        }

    @classmethod
    def _github_primary_email(cls, headers: dict[str, str]) -> str:
        emails = cls._get_json(cls.GITHUB_EMAILS_URL, headers=headers)
        if not isinstance(emails, list):
            return ''
        primary = next(
            (
                item
                for item in emails
                if item.get('primary') and item.get('verified') and item.get('email')
            ),
            None,
        )
        if primary:
            return primary['email']
        verified = next((item for item in emails if item.get('verified') and item.get('email')), None)
        return verified['email'] if verified else ''

    @classmethod
    def _get_or_create_user(cls, email: str, name: str, username_hint: str):
        existing = User.objects.filter(email__iexact=email).first()
        if existing:
            return existing

        first_name, last_name = cls._split_name(name)
        username = cls._unique_username(username_hint)
        user = User.objects.create_user(
            username=username,
            email=email,
            password=None,
            first_name=first_name,
            last_name=last_name,
        )
        user.set_unusable_password()
        user.save(update_fields=['password'])
        return user

    @staticmethod
    def _split_name(name: str) -> tuple[str, str]:
        parts = name.strip().split()
        if not parts:
            return '', ''
        return parts[0][:150], ' '.join(parts[1:])[:150]

    @staticmethod
    def _unique_username(hint: str) -> str:
        base = ''.join(ch for ch in hint.lower() if ch.isalnum() or ch in ('_', '-', '.'))
        base = (base or 'user')[:140]
        username = base
        while User.objects.filter(username__iexact=username).exists():
            username = f'{base}-{secrets.token_hex(3)}'[:150]
        return username

    @staticmethod
    def _post_json(url: str, data: dict[str, str], headers: dict[str, str] | None = None):
        try:
            response = requests.post(url, data=data, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise AuthenticationFailed(f'OAuth token exchange failed: {exc}') from exc
        except ValueError as exc:
            raise AuthenticationFailed('OAuth provider returned invalid JSON.') from exc

    @staticmethod
    def _get_json(url: str, headers: dict[str, str]):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise AuthenticationFailed(f'OAuth profile lookup failed: {exc}') from exc
        except ValueError as exc:
            raise AuthenticationFailed('OAuth provider returned invalid JSON.') from exc
