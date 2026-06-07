from rest_framework import serializers

from apps.files.models import File, FileBranch, FileVersion
from apps.users.serializers import UserSerializer
from core.validators import validate_file_path


class FileSerializer(serializers.ModelSerializer):
    tier = serializers.SerializerMethodField()
    content = serializers.CharField(max_length=100000, required=False, allow_blank=True)

    class Meta:
        model = File
        fields = (
            "id",
            "project",
            "path",
            "content",
            "language",
            "tier",
            "byte_size",
            "line_count",
            "yjs_state_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "tier",
            "byte_size",
            "line_count",
            "yjs_state_version",
            "created_at",
            "updated_at",
        )

    def get_tier(self, obj):
        return obj.tier

    def validate_path(self, value):
        validate_file_path(value)
        return value.strip("/")


class FileMetaSerializer(serializers.ModelSerializer):
    tier = serializers.SerializerMethodField()

    class Meta:
        model = File
        fields = (
            "id",
            "path",
            "language",
            "tier",
            "byte_size",
            "line_count",
            "yjs_state_version",
            "updated_at",
        )

    def get_tier(self, obj):
        return obj.tier


class FileTreeSerializer(serializers.ModelSerializer):
    tier = serializers.SerializerMethodField()

    class Meta:
        model = File
        fields = ("id", "path", "language", "byte_size", "tier")

    def get_tier(self, obj):
        return obj.tier


class FileVersionSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    label = serializers.CharField(max_length=255, required=False, allow_blank=True)
    branch_name = serializers.CharField(max_length=255)

    class Meta:
        model = FileVersion
        fields = [
            "id",
            "file",
            "branch_name",
            "snapshot_hash",
            "label",
            "source",
            "created_by",
            "created_at",
            "parent_version",
        ]
        read_only_fields = ["id", "snapshot_hash", "created_at"]


class FileVersionDetailSerializer(FileVersionSerializer):
    snapshot = serializers.CharField(max_length=100000, required=False, allow_blank=True)

    class Meta(FileVersionSerializer.Meta):
        fields = FileVersionSerializer.Meta.fields + ["snapshot"]


class FileBranchSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=255)

    class Meta:
        model = FileBranch
        fields = ["id", "name", "is_default", "created_at", "head_version"]
