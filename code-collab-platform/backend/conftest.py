"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Stand in for Redis on every test (JWT blacklist, etc.)."""
    import fakeredis

    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("apps.users.token_blacklist.get_redis_client", lambda: client)
    yield client
    client.flushall()


@pytest.fixture
def db_user(db):
    from apps.users.models import User

    return User.objects.create_user(
        email="testuser@example.com",
        display_name="Test User",
        password="SecurePass123!",
    )


@pytest.fixture
def db_workspace(db):
    """TODO Phase 1: create and return a test workspace."""
    return None


@pytest.fixture
def db_project(db):
    """TODO Phase 1: create and return a test project."""
    return None


@pytest.fixture
def db_file(db):
    """TODO Phase 1: create and return a test file."""
    return None


@pytest.fixture
def redis_client():
    """In-memory Redis stand-in for unit tests."""
    import fakeredis

    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    client.flushall()


@pytest.fixture
async def async_client():
    """
    TODO Phase 1: WebSocket test client for Channels consumers.

    Will use channels.testing.WebsocketCommunicator once collaboration
    consumers are implemented.
    """
    pytest.skip("async_client fixture not wired yet — implement in Phase 1")
