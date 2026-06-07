"""CI placeholder tests — replace with real tests in Phase 1."""

import pytest


@pytest.mark.django_db
def test_ci_placeholder():
    assert True


def test_health_import():
    from apps.core.health import health_check, readiness_check

    assert callable(health_check)
    assert callable(readiness_check)
