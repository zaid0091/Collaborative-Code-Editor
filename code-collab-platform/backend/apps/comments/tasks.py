"""Celery tasks for comment WebSocket broadcasts."""

from __future__ import annotations

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer

from apps.comments.models import Comment


def _build_payload(comment: Comment, event_type: str) -> dict:
    author = comment.author
    return {
        "type": "comment_event",
        "event": event_type,
        "comment_id": str(comment.id),
        "file_id": str(comment.file_id),
        "line_start": comment.line_start,
        "line_end": comment.line_end,
        "author": {
            "id": str(author.id) if author else None,
            "display_name": author.display_name if author else None,
        },
        "is_resolved": comment.is_resolved,
    }


@shared_task(name="comments.broadcast_event")
def broadcast_comment_event(comment_id: str, event_type: str, snapshot: dict | None = None):
    """Broadcast comment CRUD events to the file collaboration WebSocket group."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    if snapshot is not None:
        payload = snapshot
        file_id = snapshot["file_id"]
    else:
        comment = Comment.objects.select_related("author", "file").get(pk=comment_id)
        payload = _build_payload(comment, event_type)
        file_id = str(comment.file_id)

    async_to_sync(channel_layer.group_send)(
        f"file_{file_id}",
        {
            "type": "broadcast.comment_event",
            "payload": payload,
        },
    )
