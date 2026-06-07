"""Legacy health view — delegates to apps.core.health."""

from apps.core.health import health_check as health

__all__ = ["health"]
