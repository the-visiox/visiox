import hashlib

from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication


class APIKeyAuthentication(BaseAuthentication):
    keyword = 'Api-Key'

    def authenticate(self, request):
        raw_key = request.META.get('HTTP_X_API_KEY')
        if not raw_key:
            return None

        from billing.models import APIKey
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        try:
            api_key = APIKey.objects.select_related('user').get(key_hash=key_hash, is_active=True)
        except APIKey.DoesNotExist:
            return None

        api_key.last_used = timezone.now()
        api_key.save(update_fields=['last_used'])
        return (api_key.user, api_key)

    def authenticate_header(self, request):
        return self.keyword


class APIKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'billing.backends.APIKeyAuthentication'
    name = 'ApiKeyAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'apiKey',
            'in': 'header',
            'name': 'X-API-KEY',
        }
