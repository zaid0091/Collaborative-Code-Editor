import redis
from django.conf import settings

from apps.users.jwt_utils import hash_token

REFRESH_COOKIE_NAME = "refresh_token"
BLACKLIST_PREFIX = "jwt:blacklist:"


def get_redis_client():
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def is_token_blacklisted(token: str) -> bool:
    client = get_redis_client()
    return bool(client.exists(f"{BLACKLIST_PREFIX}{hash_token(token)}"))


def blacklist_token(token: str, ttl_seconds: int) -> None:
    client = get_redis_client()
    client.setex(f"{BLACKLIST_PREFIX}{hash_token(token)}", ttl_seconds, "1")
