import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("code_collab")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(
    [
        "apps.collaboration",
        "apps.execution",
        "apps.files",
        "apps.ai",
        "apps.comments",
    ],
)

from tasks import persist_updates as _persist_updates  # noqa: E402,F401
from tasks import worker_tasks as _worker_tasks  # noqa: E402,F401
