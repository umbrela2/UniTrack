import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes")


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.postgres",  # ExclusionConstraint (FP3)
    "rest_framework",
    "drf_spectacular",
    "academics",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "academic_service.urls"
WSGI_APPLICATION = "academic_service.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "academic_db"),
        "USER": os.environ.get("DB_USER", "unitrack"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "unitrack"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

LANGUAGE_CODE = "fr"
TIME_ZONE = "Africa/Algiers"
USE_I18N = True
USE_TZ = False  # heures locales (Africa/Algiers) : date + heure sans fuseau
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentification (JWT du Service 1) ---
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-only-insecure-jwt-secret")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_USER_ID_CLAIM = os.environ.get("JWT_USER_ID_CLAIM", "user_id")
JWT_ROLE_CLAIM = os.environ.get("JWT_ROLE_CLAIM", "role")
AUTH_DEV_MODE = env_bool("AUTH_DEV_MODE", False)

# --- RabbitMQ (Asynchrone) ---
RABBITMQ_ENABLED = env_bool("RABBITMQ_ENABLED", True)
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.environ.get("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.environ.get("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.environ.get("RABBITMQ_PASSWORD", "guest")
RABBITMQ_VHOST = os.environ.get("RABBITMQ_VHOST", "/")
RABBITMQ_EXCHANGE = os.environ.get("RABBITMQ_EXCHANGE", "unitrack.events")

# --- Service 5 (Notification fallback HTTP) ---
NOTIFICATION_URL = os.environ.get("NOTIFICATION_URL", "")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["academics.auth.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["academics.auth.IsAuthenticatedRole"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "UniTrack - Service 3 Academic & Timetable API",
    "DESCRIPTION": "Microservice de gestion de la structure academique, emplois du temps et conflits.",
    "VERSION": "1.0.0",
}
