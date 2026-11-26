"""Settings du microservice S4 – Attendance Management (UniTrack / WAMS).

Toute la configuration dépendant de l'environnement (ports, hôtes, secrets)
vient de variables d'environnement : rien n'est codé en dur dans la logique métier.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(key, default=None):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    return str(os.environ.get(key, default)).strip().lower() in ("1", "true", "yes", "on")


def env_int(key, default):
    return int(os.environ.get(key, default))


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "attendance",
]
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": []},
}]

# --- Base de données : attendance_db (propriété exclusive de S4) -------------
if env_bool("USE_SQLITE", False):
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
else:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "attendance_db"),
        "USER": env("DB_USER", "attendance"),
        "PASSWORD": env("DB_PASSWORD", "attendance"),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "5432"),
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
    }}

LANGUAGE_CODE = "fr"
TIME_ZONE = env("TIME_ZONE", "Africa/Algiers")
USE_I18N = False
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF ---------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["attendance.auth.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {"checkin": env("THROTTLE_CHECKIN", "60/min")},
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "attendance.exceptions.exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
SPECTACULAR_SETTINGS = {
    "TITLE": "UniTrack – S4 Attendance Management API",
    "DESCRIPTION": "Génération/validation des codes, présences, absences, appel manuel, clôture, séances non assurées.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL", False)
CORS_ALLOWED_ORIGINS = [o for o in env("CORS_ALLOWED_ORIGINS", "").split(",") if o]

# --- JWT (émis par S1 Auth & Security, validé localement ici) -----------------
JWT_ALGORITHM = env("JWT_ALGORITHM", "HS256")            # HS256 (secret partagé) ou RS256 (clé publique)
JWT_SECRET = env("JWT_SECRET", "dev-shared-secret-change-me")
JWT_PUBLIC_KEY = env("JWT_PUBLIC_KEY", "").replace("\\n", "\n")
JWT_ISSUER = env("JWT_ISSUER", "")
JWT_AUDIENCE = env("JWT_AUDIENCE", "")
JWT_ROLE_CLAIM = env("JWT_ROLE_CLAIM", "role")

# --- RabbitMQ ------------------------------------------------------------------
RABBITMQ_URL = env("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")
EVENTS_EXCHANGE = env("EVENTS_EXCHANGE", "unitrack.events")
DLX_EXCHANGE = env("DLX_EXCHANGE", "unitrack.dlx")
CONSUMER_QUEUE = env("CONSUMER_QUEUE", "attendance.academic_events")

# --- Règles métier -------------------------------------------------------------
START_EARLY_MINUTES = env_int("ATTENDANCE_START_EARLY_MINUTES", 15)     # démarrage possible N min avant l'heure prévue
TEACHER_ABSENCE_REFERENCE = env("TEACHER_ABSENCE_REFERENCE", "end")     # "end" (FP12) ou "start" (UML UC-SYS-02)
TEACHER_ABSENCE_GRACE_MINUTES = env_int("TEACHER_ABSENCE_GRACE_MINUTES", 0)
AUTO_CLOSE_GRACE_MINUTES = env_int("AUTO_CLOSE_GRACE_MINUTES", 30)      # clôture auto si l'enseignant oublie
SCHEDULER_INTERVAL_SECONDS = env_int("SCHEDULER_INTERVAL_SECONDS", 30)
OUTBOX_INTERVAL_SECONDS = env_int("OUTBOX_INTERVAL_SECONDS", 2)

LOGGING = {
    "version": 1, "disable_existing_loggers": False,
    "formatters": {"std": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "std"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
