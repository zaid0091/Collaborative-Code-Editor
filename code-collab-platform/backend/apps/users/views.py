from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.generics import CreateAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.jwt_utils import decode_token, generate_access_token, generate_refresh_token
from apps.users.models import User
from apps.users.serializers import LoginSerializer, RegisterSerializer, UserSerializer
from apps.users.token_blacklist import (
    REFRESH_COOKIE_NAME,
    blacklist_token,
    is_token_blacklisted,
)

REFRESH_MAX_AGE = 7 * 24 * 60 * 60


def _set_refresh_cookie(response, refresh_token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
        max_age=REFRESH_MAX_AGE,
    )


def _clear_refresh_cookie(response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        samesite="Lax",
    )


# SECURITY AUDIT: permission confirmed — AllowAny for public auth endpoints.
class RegisterView(CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


# SECURITY AUDIT: permission confirmed — AllowAny; credentials validated in serializer.
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        access_token = generate_access_token(user)
        refresh_token = generate_refresh_token(user)

        response = Response(
            {
                "access_token": access_token,
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )
        _set_refresh_cookie(response, refresh_token)
        return response


# SECURITY AUDIT: permission confirmed — AllowAny; refresh token validated + rotated.
class RefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME)
        if not refresh_token:
            raise AuthenticationFailed("Refresh token not provided.")

        if is_token_blacklisted(refresh_token):
            raise AuthenticationFailed("Refresh token has been revoked.")

        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise AuthenticationFailed("Invalid refresh token.")

        try:
            user = User.objects.get(id=payload["user_id"], is_active=True)
        except User.DoesNotExist as exc:
            raise AuthenticationFailed("User not found.") from exc

        new_refresh_token = generate_refresh_token(user)
        access_token = generate_access_token(user)

        blacklist_token(refresh_token, REFRESH_MAX_AGE)

        response = Response({"access_token": access_token}, status=status.HTTP_200_OK)
        _set_refresh_cookie(response, new_refresh_token)
        return response


# SECURITY AUDIT: permission confirmed — IsAuthenticated; blacklists refresh cookie.
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME)
        response = Response(status=status.HTTP_204_NO_CONTENT)

        if refresh_token:
            blacklist_token(refresh_token, REFRESH_MAX_AGE)

        _clear_refresh_cookie(response)
        return response


# SECURITY AUDIT: permission confirmed — IsAuthenticated; returns request.user only.
class MeView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user
