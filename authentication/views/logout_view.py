from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, views, response, status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError


class LogoutView(views.APIView):
    @extend_schema(
        request=inline_serializer('LogoutRequest', fields={'refresh_token': serializers.CharField()}),
        responses={204: None},
    )
    def post(self, request):
        refresh_token = request.data.get('refresh_token')
        if not refresh_token:
            return response.Response(
                {'error': 'refresh_token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return response.Response(
                {'error': 'Invalid or expired token.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return response.Response(status=status.HTTP_204_NO_CONTENT)
