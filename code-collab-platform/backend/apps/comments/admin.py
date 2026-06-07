from django.contrib import admin

from apps.comments.models import Comment, CommentReaction


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "file",
        "author",
        "line_start",
        "line_end",
        "is_resolved",
        "created_at",
    )
    list_filter = ("is_resolved", "file")
    search_fields = ("content", "author__email")
    raw_id_fields = ("file", "author", "parent", "resolved_by")


@admin.register(CommentReaction)
class CommentReactionAdmin(admin.ModelAdmin):
    list_display = ("id", "comment", "user", "emoji", "created_at")
    list_filter = ("emoji",)
    search_fields = ("comment__content", "user__email")
    raw_id_fields = ("comment", "user")
