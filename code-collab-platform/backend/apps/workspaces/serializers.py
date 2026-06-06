from rest_framework import serializers

from apps.users.serializers import UserSerializer
from apps.workspaces.models import Project, Workspace, WorkspaceMember


class WorkspaceSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)

    class Meta:
        model = Workspace
        fields = ("id", "name", "slug", "owner", "created_at")
        read_only_fields = ("id", "slug", "owner", "created_at")


class WorkspaceMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = WorkspaceMember
        fields = ("id", "user", "role", "joined_at")
        read_only_fields = ("id", "user", "joined_at")


class WorkspaceMemberCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=WorkspaceMember.ROLES,
        default=WorkspaceMember.ROLE_EDITOR,
    )


class WorkspaceMemberUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkspaceMember
        fields = ("role",)


class ProjectSerializer(serializers.ModelSerializer):
    workspace = serializers.PrimaryKeyRelatedField(
        queryset=Workspace.objects.all(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = Project
        fields = ("id", "workspace", "name", "created_at")
        read_only_fields = ("id", "created_at")
