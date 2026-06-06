from rest_framework import serializers

from apps.files.models import File


class FileSerializer(serializers.ModelSerializer):
    tier = serializers.SerializerMethodField()

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
        if ".." in value:
            raise serializers.ValidationError("Path traversal is not allowed.")
        if value.startswith("/"):
            raise serializers.ValidationError("Path must not start with '/'.")
        if "\x00" in value:
            raise serializers.ValidationError("Path contains invalid characters.")
        if len(value) > 500:
            raise serializers.ValidationError("Path must be at most 500 characters.")
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
