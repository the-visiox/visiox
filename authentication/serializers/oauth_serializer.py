from rest_framework import serializers


class OAuthLoginSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=('google', 'github'))
    code = serializers.CharField()
    redirect_uri = serializers.URLField()
