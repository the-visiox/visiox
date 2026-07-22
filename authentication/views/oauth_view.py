from drf_spectacular.utils import extend_schema
from rest_framework import response, status, views
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny

from authentication.serializers import OAuthLoginSerializer
from authentication.services import OAuthService
from authentication.throttles import LoginRateThrottle


class OAuthLoginView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]
    serializer_class = OAuthLoginSerializer

    @extend_schema(request=OAuthLoginSerializer, responses={200: dict})
    def post(self, request):
        serializer = OAuthLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            data = OAuthService.login(**serializer.validated_data)
        except ValidationError as exc:
            return response.Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        except AuthenticationFailed as exc:
            return response.Response({'detail': str(exc.detail)}, status=status.HTTP_401_UNAUTHORIZED)

        return response.Response(data, status=status.HTTP_200_OK)
