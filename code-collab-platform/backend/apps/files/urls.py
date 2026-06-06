"""Files URL configuration."""

from rest_framework.routers import DefaultRouter

from apps.files.views import FileViewSet

app_name = "files"

router = DefaultRouter()
router.register("", FileViewSet, basename="file")

urlpatterns = router.urls
