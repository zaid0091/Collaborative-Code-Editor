import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.jwt_utils import generate_access_token, generate_refresh_token
from apps.users.models import User
from apps.users.token_blacklist import REFRESH_COOKIE_NAME, blacklist_token, is_token_blacklisted


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def fake_redis(monkeypatch):
    import fakeredis

    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("apps.users.token_blacklist.get_redis_client", lambda: client)
    return client


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="alice@example.com",
        display_name="Alice",
        password="SecurePass123!",
    )


def test_register_creates_user(api_client, db, fake_redis):
    response = api_client.post(
        reverse("users:register"),
        {
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "display_name": "New User",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert User.objects.filter(email="newuser@example.com").exists()
    assert response.data["email"] == "newuser@example.com"
    assert response.data["display_name"] == "New User"


def test_login_returns_access_token_and_sets_cookie(api_client, user, fake_redis):
    response = api_client.post(
        reverse("users:login"),
        {"email": user.email, "password": "SecurePass123!"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.data
    assert response.data["user"]["email"] == user.email
    assert REFRESH_COOKIE_NAME in response.cookies


def test_refresh_rotates_token(api_client, user, fake_redis):
    login_response = api_client.post(
        reverse("users:login"),
        {"email": user.email, "password": "SecurePass123!"},
        format="json",
    )
    old_refresh = login_response.cookies[REFRESH_COOKIE_NAME].value

    api_client.cookies[REFRESH_COOKIE_NAME] = old_refresh
    refresh_response = api_client.post(reverse("users:refresh"), format="json")

    assert refresh_response.status_code == status.HTTP_200_OK
    assert "access_token" in refresh_response.data
    assert refresh_response.cookies[REFRESH_COOKIE_NAME].value != old_refresh
    assert is_token_blacklisted(old_refresh) is True


def test_logout_blacklists_token(api_client, user, fake_redis):
    login_response = api_client.post(
        reverse("users:login"),
        {"email": user.email, "password": "SecurePass123!"},
        format="json",
    )
    refresh_token = login_response.cookies[REFRESH_COOKIE_NAME].value
    access_token = login_response.data["access_token"]

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    api_client.cookies[REFRESH_COOKIE_NAME] = refresh_token

    logout_response = api_client.post(reverse("users:logout"), format="json")

    assert logout_response.status_code == status.HTTP_204_NO_CONTENT
    assert is_token_blacklisted(refresh_token) is True


def test_invalid_token_returns_401(api_client, user, fake_redis):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer invalid-token")
    response = api_client.get(reverse("users:me"))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["error"] is True


def test_blacklisted_token_rejected_on_refresh(api_client, user, fake_redis):
    refresh_token = generate_refresh_token(user)
    blacklist_token(refresh_token, 7 * 24 * 60 * 60)

    api_client.cookies[REFRESH_COOKIE_NAME] = refresh_token
    response = api_client.post(reverse("users:refresh"), format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["error"] is True


def test_me_requires_valid_access_token(api_client, user, fake_redis):
    access_token = generate_access_token(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    response = api_client.get(reverse("users:me"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["email"] == user.email
