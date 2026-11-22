"""Settings entry point.

`DJANGO_ENV=prod` loads production hardening; anything else uses dev settings.
"""

import os

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, DEBUG, env

if os.getenv("DJANGO_ENV", "dev").lower() == "prod":
    from .prod import *  # noqa: F401,F403
else:
    from .dev import *  # noqa: F401,F403

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "loggers": {
        "store": {"handlers": ["console"], "level": env("STORE_LOG_LEVEL", "INFO"), "propagate": False},
    },
}

__all__ = ["BASE_DIR", "DEBUG"]
