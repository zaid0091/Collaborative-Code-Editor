"""Comments URL configuration."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.comments.views import CommentReactionViewSet, CommentViewSet

app_name = "comments"

router = DefaultRouter()
router.register("", CommentViewSet, basename="comment")

urlpatterns = router.urls + [
    path(
        "<uuid:comment_id>/reactions/",
        CommentReactionViewSet.as_view({"get": "list", "post": "create"}),
        name="comment-reactions",
    ),
]
