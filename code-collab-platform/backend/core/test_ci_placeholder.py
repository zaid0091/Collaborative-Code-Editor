"""CI placeholder tests — replace with real tests in Phase 1."""

import pytest


@pytest.mark.django_db
def test_ci_placeholder():
    assert True


def test_health_import():
    from core.views import health

    assert callable(health)
