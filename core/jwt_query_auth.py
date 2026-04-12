"""JWT from Authorization header or `?token=` (for <img src> etc.)."""

from rest_framework_simplejwt.authentication import JWTAuthentication


class JWTAuthQueryOrHeader(JWTAuthentication):
    def get_header(self, request):
        header = super().get_header(request)
        if header is not None:
            return header
        token = request.GET.get('token')
        if token:
            return b'Bearer ' + token.encode('utf-8')
        return None
