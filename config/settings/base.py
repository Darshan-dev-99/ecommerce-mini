"""Base settings shared by every environment.

Configuration is environment driven so the same code runs:
  * locally on SQLite + in-process cache (no external services needed),
  * in Docker on PostgreSQL + Redis by setting DATABASE_URL / REDIS_URL.
"""

import importlib.util
import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(key, default=None):
    return os.getenv(key, default)


def env_bool(key, default=False):
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(key, default):
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


def env_list(key, default=()):
    raw = os.getenv(key)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def module_available(name):
    return importlib.util.find_spec(name) is not None


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------

SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-0zmm2t4*ej7s1503!5u%d2lkv)+6ajsk@6l=0x0qy-@dq$co8s",
)

DEBUG = env_bool("DJANGO_DEBUG", False)

ALLOWED_HOSTS = ["*"] if env_bool("DJANGO_ALLOW_ALL_HOSTS", True) else env_list("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "store.apps.StoreConfig",
]

MIDDLEWARE = [
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "store.context_processors.storefront",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

AUTH_USER_MODEL = "store.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"

SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
CSRF_COOKIE_HTTPONLY = False  # the frontend reads the token for fetch() calls
CSRF_FAILURE_VIEW = "store.views.common.csrf_failure"

DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024


# --------------------------------------------------------------------------
# Database: PostgreSQL when DATABASE_URL is set, SQLite otherwise
# --------------------------------------------------------------------------


def build_database():
    url = env("DATABASE_URL", "").strip()
    if not url:
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "db.sqlite3",
                "OPTIONS": {"timeout": 20},
            }
        }

    parsed = urlparse(url)
    scheme = parsed.scheme.split("+")[0]

    if scheme in {"postgres", "postgresql"}:
        if not (module_available("psycopg") or module_available("psycopg2")):
            raise RuntimeError(
                "DATABASE_URL points at PostgreSQL but neither psycopg nor psycopg2 "
                "is installed. Run: pip install 'psycopg[binary]'"
            )
        engine = (
            "django.db.backends.postgresql"
            if module_available("psycopg")
            else "django.db.backends.postgresql_psycopg2"
        )
        return {
            "default": {
                "ENGINE": engine,
                "NAME": parsed.path.lstrip("/"),
                "USER": parsed.username or "",
                "PASSWORD": parsed.password or "",
                "HOST": parsed.hostname or "localhost",
                "PORT": str(parsed.port or 5432),
                "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
                "OPTIONS": {"connect_timeout": 10},
            }
        }

    if scheme == "sqlite":
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": parsed.path.lstrip("/") or (BASE_DIR / "db.sqlite3"),
            }
        }

    raise RuntimeError(f"Unsupported DATABASE_URL scheme: {scheme}")


DATABASES = build_database()

#: Shown in the UI so it is obvious which datastore is serving requests.
DATABASE_LABEL = "PostgreSQL" if "postgresql" in DATABASES["default"]["ENGINE"] else "SQLite"


# --------------------------------------------------------------------------
# Cache: Redis when REDIS_URL is set and the client is installed
# --------------------------------------------------------------------------

REDIS_URL = env("REDIS_URL", "").strip()
REDIS_ENABLED = bool(REDIS_URL) and module_available("redis") and module_available("django_redis")

if REDIS_ENABLED:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "IGNORE_EXCEPTIONS": True,
                "SOCKET_CONNECT_TIMEOUT": 2,
                "SOCKET_TIMEOUT": 2,
            },
            "KEY_PREFIX": "ministore",
        }
    }
    CACHE_LABEL = "Redis"
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ministore-locmem",
        }
    }
    CACHE_LABEL = "In-process cache"

#: Default cache-aside TTLs (seconds).
CACHE_TTL = {
    "product_list": env_int("CACHE_TTL_PRODUCT_LIST", 60),
    "product_detail": env_int("CACHE_TTL_PRODUCT_DETAIL", 120),
    "categories": env_int("CACHE_TTL_CATEGORIES", 300),
    "brands": env_int("CACHE_TTL_BRANDS", 300),
    "home": env_int("CACHE_TTL_HOME", 45),
    "dashboard": env_int("CACHE_TTL_DASHBOARD", 20),
    "suggest": env_int("CACHE_TTL_SUGGEST", 120),
}


# --------------------------------------------------------------------------
# Django REST Framework
# --------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "suggest": "60/minute",
        "reviews": "20/hour",
        "checkout": "30/hour",
    },
    "EXCEPTION_HANDLER": "store.views.common.api_exception_handler",
}


# --------------------------------------------------------------------------
# Storefront business rules (India)
# --------------------------------------------------------------------------

STORE = {
    "name": "BazaarNoon",
    "tagline": "India's everyday marketplace",
    "currency": "INR",
    "currency_symbol": "₹",
    "locale": "en-IN",
    "support_phone": "+91 80 4718 5000",
    "support_email": "care@bazaarnoon.in",
    "gst_number": "29ABCDE1234F1Z5",
    "free_delivery_threshold": env_int("FREE_DELIVERY_THRESHOLD", 499),
    "standard_delivery_fee": env_int("STANDARD_DELIVERY_FEE", 49),
    "cod_fee": env_int("COD_FEE", 49),
    "cod_max_order_value": env_int("COD_MAX_ORDER_VALUE", 50000),
    "gst_rate": "0.18",
    "low_stock_threshold": env_int("LOW_STOCK_THRESHOLD", 5),
    "review_min_order_status": "Delivered",
}

LOW_STOCK_THRESHOLD = STORE["low_stock_threshold"]
