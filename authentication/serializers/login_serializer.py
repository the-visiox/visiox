from rest_framework import serializers

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(
                    required=True,
                    error_messages={
                        "empty": "User name should not be empty.",
                        "null": "User name is required.",
                    })
    password = serializers.CharField(
                    required=True, 
                    error_messages={
                        "empty": "Password should not be empty.",
                        "null": "Password is required.",
                    })
    