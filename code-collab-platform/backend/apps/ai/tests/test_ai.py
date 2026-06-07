import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.ai.rate_limit import check_and_consume_tokens, get_usage
from apps.ai.services import strip_secrets
from apps.execution.scheduler import FairnessScheduler
from apps.users.jwt_utils import generate_access_token
from apps.users.models import User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="ai@example.com",
        display_name="AI User",
        password="SecurePass123!",
    )


@pytest.fixture
def auth_client(api_client, user):
    token = generate_access_token(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client


@pytest.fixture
def fake_ai_redis():
    import fakeredis

    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def patched_ai_redis(monkeypatch, fake_ai_redis):
    monkeypatch.setattr("apps.ai.rate_limit._redis_client", lambda: (fake_ai_redis, 50000))
    monkeypatch.setattr("apps.ai.views._redis_client", lambda: fake_ai_redis)
    return fake_ai_redis


def test_strip_secrets_removes_openai_key():
    text = 'api_key = "sk-1234567890123456789012345678901234"'
    cleaned = strip_secrets(text)
    assert "sk-" not in cleaned
    assert "[REDACTED]" in cleaned


def test_strip_secrets_removes_bearer_token():
    text = "headers = {'Authorization': 'Bearer abc.def.ghi'}"
    cleaned = strip_secrets(text)
    assert "Bearer" not in cleaned
    assert "[REDACTED]" in cleaned


def test_strip_secrets_removes_password_assignment():
    text = "password = supersecretvalue"
    cleaned = strip_secrets(text)
    assert "supersecretvalue" not in cleaned
    assert "[REDACTED]" in cleaned


def test_token_budget_allows_within_limit(patched_ai_redis):
    assert check_and_consume_tokens("user-1", 100) is True
    usage = get_usage("user-1")
    assert usage["used"] == 100
    assert usage["remaining"] == 50000 - 100


def test_token_budget_rejects_over_limit(patched_ai_redis):
    patched_ai_redis.set("ai:tokens:user-2", 49950)
    assert check_and_consume_tokens("user-2", 100) is False


@pytest.mark.django_db
def test_detect_bugs_enqueues_to_low_queue(auth_client, patched_ai_redis, monkeypatch):
    scheduler = FairnessScheduler(redis_client=patched_ai_redis)
    monkeypatch.setattr("apps.ai.views.scheduler", scheduler)

    captured = {}

    def fake_apply_async(*args, **kwargs):
        captured["queue"] = kwargs.get("queue")
        captured["priority"] = kwargs.get("priority")

    monkeypatch.setattr("apps.ai.tasks.detect_bugs_task.apply_async", fake_apply_async)

    response = auth_client.post(
        reverse("ai:detect-bugs"),
        {"code": 'print("hello")', "language": "python"},
        format="json",
    )

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert captured["queue"] == "execution.low"
    assert captured["priority"] == 1


@pytest.mark.django_db
def test_detect_bugs_cannot_enqueue_to_high_queue(auth_client, patched_ai_redis, monkeypatch):
    scheduler = FairnessScheduler(redis_client=patched_ai_redis)
    monkeypatch.setattr("apps.ai.views.scheduler", scheduler)

    captured = {}

    def fake_apply_async(*args, **kwargs):
        captured["queue"] = kwargs.get("queue")

    monkeypatch.setattr("apps.ai.tasks.detect_bugs_task.apply_async", fake_apply_async)

    auth_client.post(
        reverse("ai:detect-bugs"),
        {"code": 'print("hello")', "language": "python"},
        format="json",
    )

    assert captured["queue"] != "execution.high"
    assert captured["queue"] == "execution.low"


@pytest.mark.django_db
def test_inline_complete_strips_secrets_before_provider_call(
    auth_client, patched_ai_redis, monkeypatch
):
    class MockProvider:
        def __init__(self):
            self.last_messages = None

        async def complete(self, messages, max_tokens=500):
            self.last_messages = messages
            return "completion"

    mock_provider = MockProvider()
    monkeypatch.setattr("apps.ai.views.get_provider", lambda: mock_provider)

    secret_code = 'key = "sk-1234567890123456789012345678901234"\nprint("hi")'
    response = auth_client.post(
        reverse("ai:complete"),
        {"code_context": secret_code, "language": "python"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    sent_content = mock_provider.last_messages[1]["content"]
    assert "sk-" not in sent_content
    assert "[REDACTED]" in sent_content
