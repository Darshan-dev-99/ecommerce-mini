"""System endpoints: cache telemetry, health and a live request simulator.

These power the /architecture page, which shows the real request path:

    Browser -> API -> cache check -> (miss) -> PostgreSQL -> cache fill
"""

import os
import time

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..cache import (
    build_key,
    bump_catalog_version,
    cache_stats,
    get_cached,
    reset_stats,
    set_cached,
)
from ..models import Brand, Category, Product
from ..serializers import BrandSerializer, CategorySerializer, ProductListSerializer


def _producer_count():
    return {
        "rows": Product.objects.filter(is_active=True).count(),
        "categories": Category.objects.filter(is_active=True).count(),
    }


class CacheStatsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        stats = cache_stats()
        stats["layers"] = [
            {
                "id": "browser",
                "label": "Browser",
                "detail": "Vanilla JS fetch() client",
                "live": True,
            },
            {
                "id": "api",
                "label": "Django REST API",
                "detail": "Storefront views",
                "live": True,
            },
            {
                "id": "cache",
                "label": stats["backend"],
                "detail": (
                    f"Versioned keys · v{stats['catalog_version']}"
                    if stats["is_redis"]
                    else "In-process fallback (set REDIS_URL for Redis)"
                ),
                "live": True,
            },
            {
                "id": "database",
                "label": stats["database"],
                "detail": "Source of truth for the catalog",
                "live": True,
            },
        ]
        stats["settings"] = {
            "redis_url_configured": bool(getattr(settings, "REDIS_URL", "")),
            "database_url_configured": "DATABASE_URL" in os.environ,
            "debug": settings.DEBUG,
        }
        return Response(stats)


class CacheWarmView(APIView):
    """Pre-compute the hot keys so the first shopper always gets a HIT."""

    permission_classes = [AllowAny]

    def post(self, request):
        started = time.perf_counter()
        warmed = []

        categories = list(Category.objects.filter(is_active=True))
        set_cached(
            "catalog:categories",
            {"all": False},
            CategorySerializer(categories, many=True).data,
            settings.CACHE_TTL["categories"],
        )
        warmed.append("catalog:categories")

        brands = list(Brand.objects.filter(is_active=True))
        set_cached(
            "catalog:brands",
            {"all": False},
            BrandSerializer(brands, many=True).data,
            settings.CACHE_TTL["brands"],
        )
        warmed.append("catalog:brands")

        bestsellers = list(
            Product.objects.filter(is_active=True, stock__gt=0)
            .select_related("brand", "category")
            .order_by("-sold_count")[:24]
        )
        set_cached(
            "catalog:products",
            {"warm": "bestsellers"},
            ProductListSerializer(bestsellers, many=True).data,
            settings.CACHE_TTL["product_list"],
        )
        warmed.append("catalog:products")

        return Response(
            {
                "message": f"Warmed {len(warmed)} cache entries in {(time.perf_counter() - started) * 1000:.0f} ms.",
                "keys": warmed,
                "backend": getattr(settings, "CACHE_LABEL", "Cache"),
            }
        )


class CacheResetView(APIView):
    """Clear telemetry and invalidate every versioned catalog key."""

    permission_classes = [AllowAny]

    def post(self, request):
        reset_stats()
        version = bump_catalog_version()
        return Response(
            {
                "message": "Telemetry reset and the catalog namespace was invalidated.",
                "catalog_version": version,
            }
        )


class SimulateRequestView(APIView):
    """Run the diagram for real and return every hop with timings."""

    permission_classes = [AllowAny]

    def post(self, request):
        probe = str(request.data.get("probe") or "demo")[:40]
        payload = {"probe": probe}
        key = build_key("system:probe", payload)
        steps = [
            {
                "id": "browser",
                "label": "Browser → GET /api/products/",
                "detail": "fetch() with credentials: same-origin",
                "ms": 0.0,
                "state": "done",
            }
        ]

        tick = time.perf_counter()
        value, hit = get_cached("system:probe", payload)
        lookup_ms = (time.perf_counter() - tick) * 1000
        steps.append(
            {
                "id": "cache",
                "label": f"API checked {getattr(settings, 'CACHE_LABEL', 'cache')}",
                "detail": key,
                "ms": round(lookup_ms, 2),
                "state": "hit" if hit else "miss",
            }
        )

        db_ms = 0.0
        if hit:
            steps.append(
                {
                    "id": "database",
                    "label": f"Skipped — served straight from cache",
                    "detail": f"{value.get('rows', 0)} products memoised",
                    "ms": 0.0,
                    "state": "skipped",
                }
            )
        else:
            tick = time.perf_counter()
            value = {"rows": _producer_count()["rows"], "at": timezone.now().isoformat()}
            db_ms = (time.perf_counter() - tick) * 1000
            steps.append(
                {
                    "id": "database",
                    "label": "Cache miss → PostgreSQL query",
                    "detail": f"SELECT COUNT(*) FROM store_product · {value['rows']} rows",
                    "ms": round(db_ms, 2),
                    "state": "done",
                }
            )
            tick = time.perf_counter()
            set_cached("system:probe", payload, value, 30)
            fill_ms = (time.perf_counter() - tick) * 1000
            steps.append(
                {
                    "id": "backfill",
                    "label": "Cache filled for the next request",
                    "detail": "TTL 30s · versioned key",
                    "ms": round(fill_ms, 2),
                    "state": "done",
                }
            )

        return Response(
            {
                "hit": hit,
                "key": key,
                "probe": probe,
                "total_ms": round(lookup_ms + db_ms, 2),
                "steps": steps,
                "stats": cache_stats(),
            }
        )


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        tick = time.perf_counter()
        db_ok, db_error = True, ""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as exc:  # pragma: no cover - depends on environment
            db_ok, db_error = False, str(exc)
        db_ms = (time.perf_counter() - tick) * 1000

        tick = time.perf_counter()
        cache_ok = True
        try:
            cache.set("health:ping", "pong", 10)
            cache_ok = cache.get("health:ping") == "pong"
        except Exception:  # pragma: no cover
            cache_ok = False
        cache_ms = (time.perf_counter() - tick) * 1000

        return Response(
            {
                "status": "ok" if db_ok and cache_ok else "degraded",
                "database": {
                    "backend": getattr(settings, "DATABASE_LABEL", "Database"),
                    "ok": db_ok,
                    "latency_ms": round(db_ms, 2),
                    "error": db_error,
                },
                "cache": {
                    "backend": getattr(settings, "CACHE_LABEL", "Cache"),
                    "ok": cache_ok,
                    "latency_ms": round(cache_ms, 2),
                },
                "server_time": timezone.now(),
            }
        )
