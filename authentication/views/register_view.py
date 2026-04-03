from drf_spectacular.utils import extend_schema
from rest_framework import views, response, status
from rest_framework.permissions import AllowAny

from authentication.serializers import RegisterSerializer
from authentication.services import AuthenticationService


class RegisterView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = RegisterSerializer

    @extend_schema(request=RegisterSerializer, responses={201: dict})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_data = AuthenticationService.sign_up(**serializer.validated_data)
        return response.Response(user_data, status=status.HTTP_201_CREATED)
