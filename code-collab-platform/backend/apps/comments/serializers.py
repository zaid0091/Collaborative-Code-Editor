"""Comment serializers."""

from __future__ import annotations

from django.db.models import Count
from django.utils import timezone
from rest_framework import serializers

from apps.comments.models import Comment, CommentReaction
from apps.files.models import File
from apps.users.serializers import UserSerializer
from core.permissions import EDITOR_ROLES, get_file_workspace_id, get_user_workspace_role

ALLOWED_EMOJIS = ["👍", "👎", "❤️", "🎉", "😕", "🚀", "👀", "✅"]


class CommentReactionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    emoji = serializers.CharField(max_length=10)

    class Meta:
        model = CommentReaction
        fields = ("id", "emoji", "user", "created_at")
        read_only_fields = ("id", "user", "created_at")

    def validate_emoji(self, value):
        if value not in ALLOWED_EMOJIS:
            raise serializers.ValidationError(f"Emoji must be one of: {', '.join(ALLOWED_EMOJIS)}")
        return value


class CommentReplySerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True, allow_null=True)
    parent_id = serializers.UUIDField(read_only=True)
    resolved_by = UserSerializer(read_only=True)
    reactions = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = (
            "id",
            "author",
            "content",
            "line_start",
            "line_end",
            "col_start",
            "col_end",
            "parent_id",
            "is_resolved",
            "resolved_by",
            "resolved_at",
            "created_at",
            "updated_at",
            "branch_name",
            "reactions",
        )
        read_only_fields = fields

    def get_reactions(self, obj):
        grouped = obj.reactions.values("emoji").annotate(count=Count("id")).order_by("emoji")
        return [{"emoji": row["emoji"], "count": row["count"]} for row in grouped]


class CommentSerializer(serializers.ModelSerializer):
    file_id = serializers.PrimaryKeyRelatedField(source="file", queryset=File.objects.all())
    author = UserSerializer(read_only=True, allow_null=True)
    content = serializers.CharField(max_length=10000)
    parent_id = serializers.PrimaryKeyRelatedField(
        source="parent",
        queryset=Comment.objects.all(),
        allow_null=True,
        required=False,
    )
    resolved_by = UserSerializer(read_only=True)
    reply_count = serializers.SerializerMethodField()
    reactions = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = (
            "id",
            "file_id",
            "author",
            "content",
            "line_start",
            "line_end",
            "col_start",
            "col_end",
            "parent_id",
            "is_resolved",
            "resolved_by",
            "resolved_at",
            "created_at",
            "updated_at",
            "branch_name",
            "reply_count",
            "reactions",
        )
        read_only_fields = (
            "id",
            "author",
            "is_resolved",
            "resolved_by",
            "resolved_at",
            "created_at",
            "updated_at",
            "reply_count",
            "reactions",
        )

    def get_reply_count(self, obj):
        if hasattr(obj, "reply_count"):
            return obj.reply_count
        return obj.replies.count()

    def get_reactions(self, obj):
        grouped = obj.reactions.values("emoji").annotate(count=Count("id")).order_by("emoji")
        return [{"emoji": row["emoji"], "count": row["count"]} for row in grouped]

    def validate(self, attrs):
        line_start = attrs.get("line_start")
        line_end = attrs.get("line_end")
        if line_start is not None and line_end is not None and line_end < line_start:
            raise serializers.ValidationError(
                {"line_end": "line_end must be greater than or equal to line_start."}
            )

        parent = attrs.get("parent")
        file = attrs.get("file")
        if parent is not None:
            if file is not None and parent.file_id != file.id:
                raise serializers.ValidationError(
                    {"parent_id": "Parent comment must belong to the same file."}
                )
            if parent.parent_id is not None:
                raise serializers.ValidationError(
                    {"parent_id": "Replies cannot be nested more than one level deep."}
                )

        return attrs

    def create(self, validated_data):
        validated_data["author"] = self.context["request"].user
        return super().create(validated_data)


class CommentUpdateSerializer(serializers.ModelSerializer):
    content = serializers.CharField(max_length=10000, required=False)

    class Meta:
        model = Comment
        fields = ("content", "is_resolved")

    def validate_content(self, value):
        request = self.context.get("request")
        if request is None or self.instance.author_id != request.user.id:
            raise serializers.ValidationError("Only the author can edit comment content.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        if "is_resolved" not in attrs or request is None:
            return attrs

        workspace_id = get_file_workspace_id(self.instance.file_id)
        role = get_user_workspace_role(request.user, workspace_id, request)
        if role not in EDITOR_ROLES:
            raise serializers.ValidationError(
                {"is_resolved": "Only workspace editors can resolve comments."}
            )
        return attrs

    def update(self, instance, validated_data):
        if "is_resolved" in validated_data:
            is_resolved = validated_data["is_resolved"]
            if is_resolved:
                instance.resolved_by = self.context["request"].user
                instance.resolved_at = timezone.now()
            else:
                instance.resolved_by = None
                instance.resolved_at = None

        return super().update(instance, validated_data)


class CommentListSerializer(CommentSerializer):
    replies = serializers.SerializerMethodField()

    class Meta(CommentSerializer.Meta):
        fields = CommentSerializer.Meta.fields + ("replies",)

    def get_replies(self, obj):
        prefetched = getattr(obj, "_prefetched_objects_cache", {})
        replies = prefetched.get("replies")
        if replies is None:
            replies = obj.replies.all()[:3]
        else:
            replies = list(replies)[:3]
        return CommentReplySerializer(replies, many=True, context=self.context).data


class CommentDetailSerializer(CommentListSerializer):
    def get_replies(self, obj):
        prefetched = getattr(obj, "_prefetched_objects_cache", {})
        replies = prefetched.get("replies", obj.replies.all())
        return CommentReplySerializer(replies, many=True, context=self.context).data
