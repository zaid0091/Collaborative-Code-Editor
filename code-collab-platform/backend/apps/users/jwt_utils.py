import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_access_token(user) -> str:
    now = datetime.now(UTC)
    payload = {
        "user_id": str(user.id),
        "email": user.email,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_ACCESS_LIFETIME_MIN),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def generate_refresh_token(user) -> str:
    now = datetime.now(UTC)
    payload = {
        "user_id": str(user.id),
        "email": user.email,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(days=settings.JWT_REFRESH_LIFETIME_DAYS),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationFailed("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationFailed("Invalid token.") from exc
