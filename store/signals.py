"""Model signals: cache invalidation and review aggregates."""

import logging

from django.db.models import Avg, Count
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import bump_catalog_version
from .models import (
    Brand,
    Category,
    Coupon,
    Order,
    Pincode,
    Product,
    ProductImage,
    Review,
)

logger = logging.getLogger("store.signals")


@receiver([post_save, post_delete], sender=Product)
@receiver([post_save, post_delete], sender=ProductImage)
@receiver([post_save, post_delete], sender=Category)
@receiver([post_save, post_delete], sender=Brand)
@receiver([post_save, post_delete], sender=Coupon)
@receiver([post_save, post_delete], sender=Pincode)
@receiver([post_save, post_delete], sender=Order)
def invalidate_catalog_cache(sender, instance, **kwargs):
    """Any catalog or order write retires every cached fragment."""
    version = bump_catalog_version()
    logger.debug("%s changed -> cache v%s", sender.__name__, version)


@receiver([post_save, post_delete], sender=Review)
def refresh_product_reviews(sender, instance, **kwargs):
    """Keep the denormalised rating on the product in sync with reviews."""
    aggregate = Review.objects.filter(product=instance.product).aggregate(
        average=Avg("rating"), total=Count("id")
    )
    Product.objects.filter(pk=instance.product_id).update(
        rating=round(aggregate["average"] or 0, 1),
        rating_count=aggregate["total"],
        review_count=aggregate["total"],
    )
