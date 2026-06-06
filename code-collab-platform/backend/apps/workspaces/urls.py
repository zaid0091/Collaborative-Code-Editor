"""Workspaces URL configuration."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.workspaces.views import ProjectViewSet, WorkspaceMemberViewSet, WorkspaceViewSet

app_name = "workspaces"

router = DefaultRouter()
router.register("", WorkspaceViewSet, basename="workspace")

member_list = WorkspaceMemberViewSet.as_view({"get": "list", "post": "create"})
member_detail = WorkspaceMemberViewSet.as_view(
    {"patch": "partial_update", "delete": "destroy"},
)

project_list = ProjectViewSet.as_view({"get": "list", "post": "create"})
project_detail = ProjectViewSet.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    },
)

urlpatterns = [
    path(
        "<uuid:workspace_pk>/members/",
        member_list,
        name="workspace-member-list",
    ),
    path(
        "<uuid:workspace_pk>/members/<int:pk>/",
        member_detail,
        name="workspace-member-detail",
    ),
    path(
        "<uuid:workspace_pk>/projects/",
        project_list,
        name="workspace-project-list",
    ),
    path(
        "<uuid:workspace_pk>/projects/<uuid:pk>/",
        project_detail,
        name="workspace-project-detail",
    ),
    *router.urls,
]
