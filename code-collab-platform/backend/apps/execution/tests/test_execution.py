import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.execution.code_scanner import scan_code
from apps.execution.models import ExecutionJob
from apps.execution.scheduler import FairnessScheduler
from apps.users.jwt_utils import generate_access_token
from apps.users.models import User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="exec@example.com",
        display_name="Exec User",
        password="SecurePass123!",
    )


@pytest.fixture
def auth_client(api_client, user):
    token = generate_access_token(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client


@pytest.fixture
def fake_scheduler_redis():
    import fakeredis

    client = fakeredis.FakeRedis(decode_responses=True)
    scheduler = FairnessScheduler(redis_client=client)
    return scheduler, client


def test_scan_code_blocks_pip_install():
    is_safe, reason = scan_code("import os\npip install requests", "python")
    assert is_safe is False
    assert reason == "Code contains a disallowed operation"


def test_scan_code_blocks_subprocess():
    is_safe, reason = scan_code("import subprocess\nsubprocess.run(['ls'])", "python")
    assert is_safe is False
    assert "disallowed" in reason


def test_scan_code_blocks_proc_read():
    is_safe, reason = scan_code('open("/proc/self/environ")', "python")
    assert is_safe is False


def test_scan_code_allows_safe_python():
    is_safe, reason = scan_code('print("hello")\nfor i in range(3):\n    print(i)', "python")
    assert is_safe is True
    assert reason is None


def test_fairness_scheduler_rejects_on_concurrent_limit(fake_scheduler_redis):
    scheduler, _client = fake_scheduler_redis
    user_id = "user-1"

    scheduler.redis.set(f"exec:fair:{user_id}:active", 2)

    allowed, stats = scheduler.check_and_reserve(user_id, "high")

    assert allowed is False
    assert stats["retry_after_sec"] == 10


def test_fairness_scheduler_allows_within_limit(fake_scheduler_redis):
    scheduler, client = fake_scheduler_redis
    user_id = "user-2"

    allowed, stats = scheduler.check_and_reserve(user_id, "high")

    assert allowed is True
    assert stats["active"] == 0
    assert int(client.get(f"exec:fair:{user_id}:pending:high") or 0) == 1


def test_fairness_on_job_complete_decrements_active(fake_scheduler_redis):
    scheduler, client = fake_scheduler_redis
    user_id = "user-3"

    client.set(f"exec:fair:{user_id}:active", 2)
    scheduler.on_job_complete(user_id, "high")

    assert int(client.get(f"exec:fair:{user_id}:active") or 0) == 1


@pytest.fixture
def patched_execution(monkeypatch, fake_scheduler_redis):
    scheduler, client = fake_scheduler_redis
    monkeypatch.setattr("apps.execution.views.scheduler", scheduler)
    monkeypatch.setattr("apps.execution.views._redis_client", lambda: client)
    return scheduler, client


@pytest.mark.django_db
def test_execute_api_rejects_unsupported_language(auth_client):
    response = auth_client.post(
        reverse("execution:execute"),
        {"code": "print(1)", "language": "ruby"},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Language not supported" in response.data["error"]


@pytest.mark.django_db
def test_execute_api_rejects_unsafe_code(auth_client):
    response = auth_client.post(
        reverse("execution:execute"),
        {"code": "import subprocess", "language": "python"},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"] == "Code contains a disallowed operation"


@pytest.mark.django_db
def test_execute_api_returns_202_with_job_id(auth_client, patched_execution, monkeypatch):
    _scheduler, _client = patched_execution

    apply_calls = []

    def fake_apply_async(*args, **kwargs):
        apply_calls.append((args, kwargs))

    monkeypatch.setattr("apps.execution.views.run_code.apply_async", fake_apply_async)

    response = auth_client.post(
        reverse("execution:execute"),
        {"code": 'print("ok")', "language": "python", "source": "ui_run"},
        format="json",
    )

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert "job_id" in response.data
    assert ExecutionJob.objects.filter(id=response.data["job_id"]).exists()
    assert apply_calls
    assert apply_calls[0][1]["queue"] == "execution.high"


@pytest.mark.django_db
def test_execute_api_respects_rate_limit(auth_client, user, patched_execution, monkeypatch):
    _scheduler, client = patched_execution
    monkeypatch.setattr("apps.execution.views.run_code.apply_async", lambda *args, **kwargs: None)

    client.set(f"exec:rate:{user.id}", 11)

    response = auth_client.post(
        reverse("execution:execute"),
        {"code": 'print("ok")', "language": "python"},
        format="json",
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.data["error"] == "Rate limit exceeded"


@pytest.mark.django_db
def test_execute_source_override_cannot_self_assign_high(
    auth_client, patched_execution, monkeypatch
):
    _scheduler, _client = patched_execution

    captured = {}

    def fake_apply_async(*args, **kwargs):
        captured["queue"] = kwargs.get("queue")
        captured["priority"] = kwargs.get("priority")

    monkeypatch.setattr("apps.execution.views.run_code.apply_async", fake_apply_async)

    response = auth_client.post(
        reverse("execution:execute"),
        {
            "code": 'print("bg")',
            "language": "python",
            "source": "background_test",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_202_ACCEPTED
    job = ExecutionJob.objects.get(id=response.data["job_id"])
    assert job.priority == ExecutionJob.PRIORITY_LOW
    assert job.source == ExecutionJob.SOURCE_BACKGROUND_TEST
    assert captured["queue"] == "execution.low"
    assert captured["priority"] == 1
