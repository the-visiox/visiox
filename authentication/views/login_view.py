from rest_framework import views, response, status
from authentication.serializers import LoginSerializer
from authentication.services import AuthenticationService

class LoginView(views.APIView):
    permission_classes = []
    authentication_classes = []
    
    def post(self, request):
        login_serializer = LoginSerializer(data=request.data)
        if not login_serializer.is_valid():
            return response.Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"error": "Invalid username or password"}
            )
            
        user_login_data = AuthenticationService.login(**login_serializer.validated_data)
        return response.Response(
            status=status.HTTP_200_OK,
            data=user_login_data
        )