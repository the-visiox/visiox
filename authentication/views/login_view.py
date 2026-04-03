from drf_spectacular.utils import extend_schema
from rest_framework import views, response, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny

from authentication.serializers import LoginSerializer
from authentication.services import AuthenticationService


class LoginView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = LoginSerializer

    @extend_schema(request=LoginSerializer, responses={200: dict})
    def post(self, request):
        login_serializer = LoginSerializer(data=request.data)
        if not login_serializer.is_valid():
            return response.Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"error": "Invalid username or password"},
            )
        try:
            user_login_data = AuthenticationService.login(**login_serializer.validated_data)
        except AuthenticationFailed as exc:
            detail = exc.detail
            if isinstance(detail, list) and detail:
                detail = str(detail[0])
            else:
                detail = str(detail)
            return response.Response({"detail": detail}, status=status.HTTP_401_UNAUTHORIZED)
        return response.Response(status=status.HTTP_200_OK, data=user_login_data)