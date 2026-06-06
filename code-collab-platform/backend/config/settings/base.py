"""
Shared Django settings.
"""

from pathlib import Path

import environ

env = environ.Env(
    DEBUG=(bool, False),
    JWT_ACCESS_LIFETIME_MIN=(int, 15),
    JWT_REFRESH_LIFETIME_DAYS=(int, 7),
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

environ.Env.read_env(BASE_DIR.parent / ".env")

SECRET_KEY = env("SECRET_KEY", default="django-insecure-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "channels",
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.users",
    "apps.workspaces",
    "apps.collaboration",
    "apps.files",
    "apps.execution",
    "apps.ai",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.JWTAuthMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Redis
REDIS_URL = env("REDIS_URL", default="redis://redis:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    },
}

# Channels
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [env("REDIS_URL", default="redis://redis:6379/0")],
            "capacity": 1500,
            "expiry": 60,
        },
    },
}

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "core.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
}

JWT_ACCESS_LIFETIME_MIN = env("JWT_ACCESS_LIFETIME_MIN")
JWT_REFRESH_LIFETIME_DAYS = env("JWT_REFRESH_LIFETIME_DAYS")

# Execution queue names (also used by Celery routes)
EXEC_HIGH_QUEUE = env("EXEC_HIGH_QUEUE", default="execution.high")
EXEC_LOW_QUEUE = env("EXEC_LOW_QUEUE", default="execution.low")

# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "crdt.*": {"queue": "crdt.persist"},
    "execution.*": {"queue": EXEC_HIGH_QUEUE},
    "tasks.worker_tasks.persist_updates": {"queue": "crdt.persist"},
    "tasks.worker_tasks.compact_snapshot": {"queue": "crdt.persist"},
    "tasks.worker_tasks.run_code": {"queue": EXEC_HIGH_QUEUE},
    "tasks.worker_tasks.run_ai_analysis": {"queue": EXEC_LOW_QUEUE},
}
CELERY_TASK_QUEUE_MAX_PRIORITY = 10
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

from tasks.beat_schedule import CELERY_BEAT_SCHEDULE  # noqa: E402

# WebSocket abuse
WS_MAX_MSG_PER_SEC = env.int("WS_MAX_MSG_PER_SEC", default=60)
WS_MAX_UPDATE_PER_SEC = env.int("WS_MAX_UPDATE_PER_SEC", default=30)
WS_ABUSE_STRIKE_BAN_MIN = env.int("WS_ABUSE_STRIKE_BAN_MIN", default=5)
WS_ABUSE_MAX_STRIKES = env.int("WS_ABUSE_MAX_STRIKES", default=3)

# CRDT persistence
YJS_FLUSH_INTERVAL_SEC = env.int("YJS_FLUSH_INTERVAL_SEC", default=5)
YJS_FLUSH_OP_THRESHOLD = env.int("YJS_FLUSH_OP_THRESHOLD", default=50)
YJS_COMPACT_OP_THRESHOLD = env.int("YJS_COMPACT_OP_THRESHOLD", default=200)
YJS_COMPACT_INTERVAL_SEC = env.int("YJS_COMPACT_INTERVAL_SEC", default=300)
YJS_IDLE_COMPACT_SEC = env.int("YJS_IDLE_COMPACT_SEC", default=30)

# Execution
EXECUTION_TIMEOUT_SEC = env.int("EXECUTION_TIMEOUT_SEC", default=5)
EXECUTION_MEMORY_MB = env.int("EXECUTION_MEMORY_MB", default=256)
EXECUTION_RATE_LIMIT = env.int("EXECUTION_RATE_LIMIT", default=10)
EXEC_FAIR_MAX_CONCURRENT = env.int("EXEC_FAIR_MAX_CONCURRENT", default=2)
EXEC_FAIR_MAX_PENDING_HIGH = env.int("EXEC_FAIR_MAX_PENDING_HIGH", default=3)
EXEC_FAIR_MAX_PENDING_LOW = env.int("EXEC_FAIR_MAX_PENDING_LOW", default=10)

# AI
AI_PROVIDER = env("AI_PROVIDER", default="openai")
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
