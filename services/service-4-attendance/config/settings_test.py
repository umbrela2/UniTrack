from .settings import *  # noqa

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
JWT_ALGORITHM = "HS256"
JWT_SECRET = "test-secret"
JWT_PUBLIC_KEY = ""
JWT_ISSUER = ""
JWT_AUDIENCE = ""
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"checkin": "100000/min"}}
