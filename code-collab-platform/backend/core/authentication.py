from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.users.jwt_utils import decode_token
from apps.users.models import User
from apps.users.token_blacklist import is_token_blacklisted


class JWTAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith(f"{self.keyword} "):
            return None

        token = auth_header[len(self.keyword) + 1 :].strip()
        if not token:
            return None

        if is_token_blacklisted(token):
            raise AuthenticationFailed("Token has been revoked.")

        payload = decode_token(token)
        if payload.get("type") != "access":
            raise AuthenticationFailed("Invalid access token.")

        try:
            user = User.objects.get(id=payload["user_id"], is_active=True)
        except User.DoesNotExist as exc:
            raise AuthenticationFailed("User not found.") from exc

        return (user, token)

    def authenticate_header(self, request):
        return self.keyword
