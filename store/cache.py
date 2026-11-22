"""Cache-aside helpers for the storefront.

Request path:

    Browser ──► API view ──► cache.get(key)
                              ├─ HIT  ──► return cached JSON
                              └─ MISS ──► PostgreSQL query ──► cache.set(key) ──► return

Every catalog write bumps a version number that is part of every key, so a
single `incr` invalidates the whole namespace without scanning keys.

The helpers are backend agnostic: Redis when `REDIS_URL` is configured,
otherwise Django's in-process cache, so the app also runs without services.
"""

import hashlib
import json
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("store.cache")

VERSION_KEY = "catalog:version"
STATS_KEY = "telemetry:cache"
STATS_TTL = 60 * 60 * 24


# --------------------------------------------------------------------------
# Versioned keys
# --------------------------------------------------------------------------


def catalog_version() -> int:
    try:
        return int(cache.get(VERSION_KEY) or 1)
    except (TypeError, ValueError):
        return 1


def bump_catalog_version() -> int:
    """Invalidate every cached catalog fragment in one atomic step."""
    try:
        version = cache.incr(VERSION_KEY)
    except (ValueError, NotImplementedError):
        version = catalog_version() + 1
        cache.set(VERSION_KEY, version, None)
    logger.debug("catalog cache version -> %s", version)
    return version


def build_key(namespace: str, payload=None) -> str:
    raw = json.dumps(payload or {}, sort_keys=True, default=str)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{namespace}:v{catalog_version()}:{digest}"


# --------------------------------------------------------------------------
# Telemetry (shown on the /architecture page)
# --------------------------------------------------------------------------


def _bump_stat(field: str) -> None:
    data = cache.get(STATS_KEY) or {"hits": 0, "misses": 0, "sets": 0}
    data[field] = data.get(field, 0) + 1
    cache.set(STATS_KEY, data, STATS_TTL)


def _key_count() -> int:
    if getattr(settings, "REDIS_ENABLED", False):
        try:
            from django_redis import get_redis_connection

            return int(get_redis_connection("default").dbsize())
        except Exception:  # pragma: no cover - redis unreachable
            return 0
    raw = getattr(cache, "_cache", None)
    try:
        return len(raw) if raw is not None else 0
    except TypeError:  # pragma: no cover
        return 0


def cache_stats() -> dict:
    data = cache.get(STATS_KEY) or {"hits": 0, "misses": 0, "sets": 0}
    hits, misses = int(data.get("hits", 0)), int(data.get("misses", 0))
    total = hits + misses
    return {
        "backend": getattr(settings, "CACHE_LABEL", "Cache"),
        "is_redis": bool(getattr(settings, "REDIS_ENABLED", False)),
        "database": getattr(settings, "DATABASE_LABEL", "Database"),
        "hits": hits,
        "misses": misses,
        "sets": int(data.get("sets", 0)),
        "requests": total,
        "hit_rate": round(hits / total * 100, 1) if total else 0.0,
        "keys": _key_count(),
        "catalog_version": catalog_version(),
        "ttls": dict(getattr(settings, "CACHE_TTL", {})),
    }


def reset_stats() -> None:
    cache.delete(STATS_KEY)


# --------------------------------------------------------------------------
# Cache-aside primitives
# --------------------------------------------------------------------------


def get_cached(namespace: str, payload=None):
    """Return (value, hit) for a cache lookup."""
    key = build_key(namespace, payload)
    value = cache.get(key)
    if value is not None:
        _bump_stat("hits")
        logger.debug("cache HIT %s", key)
        return value, True
    _bump_stat("misses")
    logger.debug("cache MISS %s", key)
    return None, False


def set_cached(namespace: str, payload, value, ttl: int) -> None:
    cache.set(build_key(namespace, payload), value, ttl)
    _bump_stat("sets")


def cache_aside(namespace: str, payload, producer, ttl: int):
    """The whole pattern in one call: lookup, fall through, backfill."""
    value, hit = get_cached(namespace, payload)
    if hit:
        return value, True
    value = producer()
    set_cached(namespace, payload, value, ttl)
    return value, False


def invalidate_namespace() -> None:
    bump_catalog_version()
