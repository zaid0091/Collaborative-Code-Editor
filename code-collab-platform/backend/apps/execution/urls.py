"""Execution URL configuration."""

from django.urls import path

from apps.execution.views import ExecuteView, ExecutionJobView

app_name = "execution"

urlpatterns = [
    path("", ExecuteView.as_view(), name="execute"),
    path("<uuid:job_id>/", ExecutionJobView.as_view(), name="job-detail"),
]
