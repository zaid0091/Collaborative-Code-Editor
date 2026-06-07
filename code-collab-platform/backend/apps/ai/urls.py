"""AI URL configuration."""

from django.urls import path

from apps.ai.views import (
    AIUsageView,
    DetectBugsResultView,
    DetectBugsView,
    ExplainSelectionView,
    InlineCompleteView,
)

app_name = "ai"

urlpatterns = [
    path("complete/", InlineCompleteView.as_view(), name="complete"),
    path("explain/", ExplainSelectionView.as_view(), name="explain"),
    path("detect-bugs/", DetectBugsView.as_view(), name="detect-bugs"),
    path("detect-bugs/<str:job_id>/", DetectBugsResultView.as_view(), name="detect-bugs-result"),
    path("usage/", AIUsageView.as_view(), name="usage"),
]
