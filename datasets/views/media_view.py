import mimetypes
import secrets

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken

from core.access import project_access_q
from datasets.models import Media


class MediaMetadataView(APIView):
    """Return storage metadata needed by the remote inference agent."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @staticmethod
    def _bearer_token(request):
        authorization = request.headers.get('Authorization', '')
        scheme, _, token = authorization.partition(' ')
        if scheme.lower() != 'bearer':
            return ''
        return token.strip()

    def _authorized_user(self, request):
        token = self._bearer_token(request)
        agent_token = getattr(settings, 'INFERENCE_AGENT_TOKEN', '')
        if agent_token and token and secrets.compare_digest(token, agent_token):
            return None, True

        try:
            authenticated = JWTAuthentication().authenticate(request)
        except (AuthenticationFailed, InvalidToken):
            return None, False
        if authenticated is None:
            return None, False
        return authenticated[0], True

    def get(self, request, media_id):
        user, authorized = self._authorized_user(request)
        if not authorized:
            return Response(
                {'error': 'Invalid inference agent token.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        media_query = Media.objects.select_related('dataset__project')
        if user is not None:
            media_query = media_query.filter(
                project_access_q(user, 'dataset__project__')
            ).distinct()
        media = media_query.filter(pk=media_id).first()
        if media is None:
            return Response(
                {'error': 'Media not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        storage_key = media.file.name
        content_type = mimetypes.guess_type(
            media.original_filename or storage_key
        )[0] or 'application/octet-stream'
        bucket = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'visiox-media')
        return Response({
            'id': media.id,
            'media_id': media.id,
            'dataset': media.dataset_id,
            'dataset_id': media.dataset_id,
            'project_id': media.dataset.project_id,
            'type': media.type,
            'filename': media.original_filename or storage_key.rsplit('/', 1)[-1],
            'original_filename': media.original_filename,
            'width': media.width,
            'height': media.height,
            'file_size': media.file_size,
            'bucket': bucket,
            'storage_key': storage_key,
            'object_key': storage_key,
            'key': storage_key,
            'content_type': content_type,
            'metadata': media.metadata,
        })
