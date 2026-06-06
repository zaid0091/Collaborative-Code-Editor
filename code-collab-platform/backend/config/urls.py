"""Root URL configuration."""

from django.urls import include, path

from core.health import HealthView

urlpatterns = [
    path("health/", HealthView.as_view()),
    path("api/auth/", include("apps.users.urls")),
    path("api/workspaces/", include("apps.workspaces.urls")),
    path("api/files/", include("apps.files.urls")),
    path("api/execute/", include("apps.execution.urls")),
]
