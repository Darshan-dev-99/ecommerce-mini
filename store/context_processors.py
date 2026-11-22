"""Storefront context available to every template."""

from django.conf import settings


def storefront(request):
    store = dict(settings.STORE)
    return {
        "STORE": store,
        "CACHE_LABEL": getattr(settings, "CACHE_LABEL", "Cache"),
        "DATABASE_LABEL": getattr(settings, "DATABASE_LABEL", "Database"),
        "GST_RATE": store["gst_rate"],
    }
