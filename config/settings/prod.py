"""Production settings - enabled with DJANGO_ENV=prod."""

import os

from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE, STATIC_ROOT, module_available

DEBUG = False

ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
if os.getenv("DJANGO_ALLOW_ALL_HOSTS", "1").strip().lower() in {"1", "true", "yes", "on"}:
    ALLOWED_HOSTS = ALLOWED_HOSTS or ["*"]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
SECURE_HSTS_SECONDS = 31536000 if os.getenv("DJANGO_ENABLE_HSTS") == "1" else 0

# Gunicorn does not serve static files, so ship the collected assets through
# WhiteNoise when it is installed (it is part of the Docker image).
if module_available("whitenoise"):
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
    WHITENOISE_MAX_AGE = 60 * 60 * 24 * 30
    WHITENOISE_ROOT = str(STATIC_ROOT)
