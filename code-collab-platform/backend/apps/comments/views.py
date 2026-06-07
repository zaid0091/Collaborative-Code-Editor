"""Comment REST API views."""

from __future__ import annotations

from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.comments.models import Comment, CommentReaction
from apps.comments.permissions import (
    CanCreateComment,
    CanResolveComment,
    IsCommentAuthor,
    IsCommentAuthorOrWorkspaceOwner,
)
from apps.comments.serializers import (
    ALLOWED_EMOJIS,
    CommentDetailSerializer,
    CommentListSerializer,
    CommentReactionSerializer,
    CommentSerializer,
    CommentUpdateSerializer,
)
from apps.comments.tasks import _build_payload, broadcast_comment_event
from core.permissions import IsWorkspaceMember, get_file_workspace_id


# SECURITY AUDIT: permission confirmed — IsAuthenticated + IsWorkspaceMember/Editor;
# queryset scoped to request.user workspace memberships.
class CommentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsWorkspaceMember]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def initial(self, request, *args, **kwargs):
        self.workspace_id = self._resolve_workspace_id(request, kwargs)
        super().initial(request, *args, **kwargs)

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), IsWorkspaceMember(), CanCreateComment()]
        if self.action == "destroy":
            return [IsAuthenticated(), IsWorkspaceMember(), IsCommentAuthorOrWorkspaceOwner()]
        return [IsAuthenticated(), IsWorkspaceMember()]

    def _resolve_workspace_id(self, request, kwargs):
        comment_id = kwargs.get("pk")
        if comment_id:
            file_id = (
                Comment.objects.filter(pk=comment_id).values_list("file_id", flat=True).first()
            )
            if file_id:
                return get_file_workspace_id(file_id)
            return None

        file_id = request.query_params.get("file_id")
        if not file_id and request.method in ("POST", "PUT", "PATCH"):
            file_id = request.data.get("file_id")
        if file_id:
            return get_file_workspace_id(file_id)
        return None

    def get_queryset(self):
        replies_queryset = (
            Comment.objects.select_related("author", "resolved_by")
            .prefetch_related("reactions")
            .order_by("created_at")
        )

        queryset = (
            Comment.objects.select_related("author", "resolved_by", "file__project__workspace")
            .filter(file__project__workspace__members__user=self.request.user)
            .prefetch_related("reactions", Prefetch("replies", queryset=replies_queryset))
            .annotate(reply_count=Count("replies"))
            .distinct()
        )

        if self.action == "list":
            queryset = queryset.filter(parent__isnull=True)

            file_id = self.request.query_params.get("file_id")
            if not file_id:
                return queryset.none()

            queryset = queryset.filter(file_id=file_id)

            branch_name = self.request.query_params.get("branch_name", "main")
            queryset = queryset.filter(branch_name=branch_name)

            resolved = self.request.query_params.get("resolved")
            if resolved is not None:
                if resolved.lower() in ("true", "1", "yes"):
                    queryset = queryset.filter(is_resolved=True)
                elif resolved.lower() in ("false", "0", "no"):
                    queryset = queryset.filter(is_resolved=False)

            range_start = self.request.query_params.get("line_start")
            range_end = self.request.query_params.get("line_end")
            if range_start is not None and range_end is not None:
                queryset = queryset.filter(
                    line_start__lte=int(range_end),
                    line_end__gte=int(range_start),
                )

            queryset = queryset.order_by("created_at")

        return queryset

    def get_serializer_class(self):
        if self.action in ("partial_update", "update"):
            return CommentUpdateSerializer
        if self.action == "retrieve":
            return CommentDetailSerializer
        if self.action == "list":
            return CommentListSerializer
        return CommentSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save()
        broadcast_comment_event.delay(str(comment.id), "created")
        return Response(
            CommentDetailSerializer(comment, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        comment = self.get_object()

        if "content" in request.data and not IsCommentAuthor().has_object_permission(
            request, self, comment
        ):
            return Response(
                {"detail": "Only the author can edit comment content."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if "is_resolved" in request.data and not CanResolveComment().has_object_permission(
            request, self, comment
        ):
            return Response(
                {"detail": "Only workspace editors can resolve comments."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CommentUpdateSerializer(
            comment,
            data=request.data,
            partial=True,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        comment.refresh_from_db()
        broadcast_comment_event.delay(str(comment.id), "updated")
        return Response(
            CommentDetailSerializer(comment, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )

    def destroy(self, request, *args, **kwargs):
        comment = self.get_object()
        has_replies = comment.replies.exists()

        if has_replies:
            comment.content = "[deleted]"
            comment.author = None
            comment.save(update_fields=["content", "author", "updated_at"])
            broadcast_comment_event.delay(str(comment.id), "deleted")
        else:
            snapshot = _build_payload(comment, "deleted")
            comment_id = str(comment.id)
            comment.delete()
            broadcast_comment_event.delay(comment_id, "deleted", snapshot=snapshot)

        return Response(status=status.HTTP_204_NO_CONTENT)


# SECURITY AUDIT: permission confirmed — IsAuthenticated + IsWorkspaceMember (viewers may react).
class CommentReactionViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsWorkspaceMember]

    def initial(self, request, *args, **kwargs):
        comment_id = kwargs.get("comment_id")
        comment = get_object_or_404(
            Comment.objects.select_related("file__project__workspace"),
            pk=comment_id,
        )
        self.comment = comment
        self.workspace_id = comment.file.project.workspace_id
        super().initial(request, *args, **kwargs)

    def list(self, request, comment_id=None):
        reactions = (
            CommentReaction.objects.filter(comment=self.comment)
            .select_related("user")
            .order_by("emoji", "created_at")
        )

        grouped: dict[str, dict] = {}
        for reaction in reactions:
            bucket = grouped.setdefault(
                reaction.emoji,
                {"emoji": reaction.emoji, "count": 0, "users": []},
            )
            bucket["count"] += 1
            bucket["users"].append(reaction.user.display_name)

        return Response(list(grouped.values()))

    def create(self, request, comment_id=None):
        emoji = request.data.get("emoji")
        if emoji not in ALLOWED_EMOJIS:
            return Response(
                {"emoji": [f"Emoji must be one of: {', '.join(ALLOWED_EMOJIS)}"]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reaction, created = CommentReaction.objects.get_or_create(
            comment=self.comment,
            user=request.user,
            emoji=emoji,
        )

        if not created:
            reaction.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        broadcast_comment_event.delay(str(self.comment.id), "reaction_added")
        return Response(
            CommentReactionSerializer(reaction, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )
