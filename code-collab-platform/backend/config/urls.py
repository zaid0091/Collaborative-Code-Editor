"""Root URL configuration."""

from django.urls import include, path

from apps.core.health import health_check, readiness_check

urlpatterns = [
    path("health/", health_check),
    path("ready/", readiness_check),
    path("", include("django_prometheus.urls")),
    path("api/auth/", include("apps.users.urls")),
    path("api/workspaces/", include("apps.workspaces.urls")),
    path("api/files/", include("apps.files.urls")),
    path("api/execute/", include("apps.execution.urls")),
    path("api/ai/", include("apps.ai.urls")),
    path("api/comments/", include("apps.comments.urls")),
]
