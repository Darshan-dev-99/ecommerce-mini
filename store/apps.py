from django.apps import AppConfig


class StoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "store"
    verbose_name = "BazaarNoon Storefront"

    def ready(self):
        # Importing the signal handlers registers cache invalidation hooks.
        from . import signals  # noqa: F401
