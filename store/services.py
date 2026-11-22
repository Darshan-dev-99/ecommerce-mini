"""Business logic: money, checkout, order lifecycle and returns.

Everything that must succeed or fail together lives inside a single
`transaction.atomic()` block, with `select_for_update()` on the products whose
stock is being changed.
"""

import datetime
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.utils import timezone
from rest_framework import serializers

from .cache import bump_catalog_version
from .models import (
    Address,
    Cart,
    Coupon,
    Order,
    OrderEvent,
    OrderItem,
    Pincode,
    Product,
    RecentlyViewed,
    ReturnRequest,
    inr,
)

logger = logging.getLogger("store.services")
STORE = settings.STORE
GST_RATE = Decimal(str(STORE["gst_rate"]))


class CheckoutError(serializers.ValidationError):
    """User-facing checkout problem (HTTP 400)."""


#: Keys of a quote that map 1:1 onto Order money columns.
BILLING_FIELDS = (
    "subtotal",
    "discount_amount",
    "delivery_fee",
    "cod_fee",
    "gst_amount",
    "total_amount",
)


# --------------------------------------------------------------------------
# Money
# --------------------------------------------------------------------------


def gst_component(amount_inclusive) -> Decimal:
    """GST already contained in an inclusive price."""
    amount = inr(amount_inclusive)
    return inr(amount - (amount / (1 + GST_RATE)))


def delivery_fee_for(subtotal, products=()) -> Decimal:
    subtotal = inr(subtotal)
    if subtotal <= 0:
        return Decimal("0.00")
    if subtotal >= Decimal(STORE["free_delivery_threshold"]):
        return Decimal("0.00")
    if products and all(getattr(p, "free_delivery", False) for p in products):
        return Decimal("0.00")
    return inr(STORE["standard_delivery_fee"])


def quote(subtotal, coupon=None, payment_method=Order.PaymentMethod.COD, products=()) -> dict:
    """The single source of truth for every money figure in the app."""
    subtotal = inr(subtotal)
    discount = coupon.discount_for(subtotal) if coupon else Decimal("0.00")
    delivery = delivery_fee_for(subtotal, products)
    cod_fee = (
        inr(STORE["cod_fee"])
        if payment_method == Order.PaymentMethod.COD and subtotal > 0
        else Decimal("0.00")
    )
    total = inr(subtotal - discount + delivery + cod_fee)
    return {
        "subtotal": subtotal,
        "discount_amount": discount,
        "delivery_fee": delivery,
        "cod_fee": cod_fee,
        "total_amount": total,
        "gst_amount": gst_component(total),
        "free_delivery_gap": max(
            Decimal("0.00"),
            Decimal(STORE["free_delivery_threshold"]) - subtotal,
        ),
    }


def pincode_info(raw_pincode) -> Pincode | None:
    code = "".join(ch for ch in str(raw_pincode or "") if ch.isdigit())
    if len(code) != 6:
        return None
    return Pincode.objects.filter(pincode=code, is_serviceable=True).first()


def estimated_delivery(products, serviceable: Pincode | None):
    """Delivery date estimate: product SLA and pincode ETA, whichever is slower."""
    today = timezone.localdate()
    product_days = max((p.delivery_days for p in products), default=3)
    pincode_days = serviceable.eta_max_days if serviceable else 0
    return today + datetime.timedelta(days=max(product_days, pincode_days or 0))


# --------------------------------------------------------------------------
# Coupons
# --------------------------------------------------------------------------


def validate_coupon(code, user, subtotal, *, cart=None) -> tuple[Coupon, Decimal]:
    code = (code or "").strip().upper()
    if not code:
        raise CheckoutError({"detail": "Enter a coupon code."})

    try:
        coupon = Coupon.objects.get(code=code)
    except Coupon.DoesNotExist:
        raise CheckoutError({"detail": f"Coupon {code} does not exist."})

    if not coupon.is_live:
        raise CheckoutError({"detail": f"Coupon {code} has expired or is no longer valid."})

    subtotal = inr(subtotal)
    if subtotal < coupon.min_order_value:
        shortfall = inr(coupon.min_order_value - subtotal)
        raise CheckoutError(
            {"detail": f"Add items worth \u20b9{shortfall} more to use {code}."}
        )

    used = Order.objects.filter(
        user=user, coupon_code=code
    ).exclude(status=Order.Status.CANCELLED).count()
    if coupon.per_user_limit and used >= coupon.per_user_limit:
        raise CheckoutError(
            {"detail": f"You have already used {code} {used} time(s)."}
        )

    discount = coupon.discount_for(subtotal)
    if discount <= 0:
        raise CheckoutError({"detail": f"Coupon {code} gives no discount on this order."})
    return coupon, discount


# --------------------------------------------------------------------------
# Checkout
# --------------------------------------------------------------------------


def _snapshot_address(address: Address) -> dict:
    return {
        "shipping_name": address.full_name,
        "shipping_phone": address.phone,
        "shipping_line1": address.line1,
        "shipping_line2": address.line2,
        "shipping_city": address.city,
        "shipping_state": address.state,
        "shipping_pincode": address.pincode,
    }


def log_event(order, status, note="", location="") -> OrderEvent:
    return OrderEvent.objects.create(
        order=order, status=status, note=note, location=location
    )


@transaction.atomic
def checkout(user, *, address: Address, payment_method: str, coupon_code: str = "") -> Order:
    """Turn the cart into an order - atomically.

    Order rows, items, stock movements, coupon usage and cart clearing either
    all commit or all roll back.
    """
    cart, _ = Cart.objects.get_or_create(user=user)
    items = list(cart.items.filter(saved_for_later=False).select_related("product"))

    if not items:
        raise CheckoutError({"detail": "Your cart is empty."})

    product_ids = sorted({item.product_id for item in items})
    locked = {
        p.pk: p
        for p in Product.objects.select_for_update().filter(pk__in=product_ids)
    }

    problems, adjusted = [], []
    for item in items:
        product = locked.get(item.product_id)
        if product is None or not product.is_active:
            problems.append(f"{item.product.name} is no longer available.")
        elif product.stock < item.quantity:
            if product.stock == 0:
                problems.append(f"{product.name} is out of stock.")
            else:
                problems.append(
                    f"Only {product.stock} left of {product.name} "
                    f"(you asked for {item.quantity})."
                )
        else:
            adjusted.append((item, product))

    if problems:
        raise CheckoutError({"detail": " ".join(problems), "items": problems})

    products = [product for _, product in adjusted]
    subtotal = inr(sum((product.price * item.quantity for item, product in adjusted), Decimal("0")))

    coupon = None
    if coupon_code:
        coupon, _ = validate_coupon(coupon_code, user, subtotal, cart=cart)
    elif cart.coupon_id:
        try:
            coupon, _ = validate_coupon(cart.coupon.code, user, subtotal, cart=cart)
        except CheckoutError:
            coupon = None

    totals = quote(subtotal, coupon=coupon, payment_method=payment_method, products=products)
    billing = {field: totals[field] for field in BILLING_FIELDS}

    cod_blocked = (
        payment_method == Order.PaymentMethod.COD
        and totals["total_amount"] > Decimal(STORE["cod_max_order_value"])
    )
    if cod_blocked:
        raise CheckoutError(
            {"detail": "Cash on Delivery is not available above "
                       f"\u20b9{STORE['cod_max_order_value']}. Please pay online."}
        )

    serviceable = pincode_info(address.pincode)

    order = Order.objects.create(
        user=user,
        payment_method=payment_method,
        payment_status=(
            Order.PaymentStatus.PENDING
            if payment_method == Order.PaymentMethod.COD
            else Order.PaymentStatus.PAID
        ),
        payment_reference=(
            "" if payment_method == Order.PaymentMethod.COD
            else f"PAY{timezone.now():%y%m%d%H%M%S}{user.pk:03d}"
        ),
        coupon=coupon,
        coupon_code=coupon.code if coupon else "",
        delivery_eta=estimated_delivery(products, serviceable),
        **billing,
        **_snapshot_address(address),
    )

    OrderItem.objects.bulk_create(
        [
            OrderItem(
                order=order,
                product=product,
                product_name=product.name,
                product_brand=product.brand.name if product.brand_id else "",
                image_url=product.image_url,
                unit_price=product.price,
                unit_mrp=product.mrp,
                quantity=item.quantity,
            )
            for item, product in adjusted
        ]
    )

    for item, product in adjusted:
        product.stock -= item.quantity
        product.sold_count += item.quantity
        product.save(update_fields=["stock", "sold_count", "updated_at"])

    if coupon:
        Coupon.objects.filter(pk=coupon.pk).update(used_count=F("used_count") + 1)

    log_event(
        order,
        Order.Status.PLACED,
        note=f"Order confirmed · {order.get_payment_method_display()}",
        location=f"{order.shipping_city}, {order.shipping_pincode}",
    )

    cart.items.all().delete()
    cart.coupon = None
    cart.save(update_fields=["coupon", "updated_at"])

    logger.info("order %s placed by %s for %s", order.order_number, user.pk, order.total_amount)
    return order


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------


@transaction.atomic
def cancel_order(order: Order, *, by_admin: bool = False, reason: str = "") -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)

    if not order.is_cancellable:
        raise serializers.ValidationError(
            {
                "detail": (
                    f"Order {order.order_number} is '{order.status}' and can no longer be "
                    "cancelled. Orders can be cancelled until they are shipped."
                )
            }
        )

    order.status = Order.Status.CANCELLED
    order.cancelled_at = timezone.now()
    order.cancel_reason = (reason or ("Cancelled by store" if by_admin else "Cancelled by customer"))[:200]
    if order.payment_status == Order.PaymentStatus.PAID:
        order.payment_status = Order.PaymentStatus.REFUNDED
    order.save(update_fields=["status", "cancelled_at", "cancel_reason", "payment_status", "updated_at"])

    for item in order.items.all():
        Product.objects.filter(pk=item.product_id).update(
            stock=F("stock") + item.quantity,
            sold_count=Greatest(F("sold_count") - item.quantity, Value(0)),
        )
    bump_catalog_version()  # .update() bypasses model signals

    log_event(order, Order.Status.CANCELLED, note=order.cancel_reason)
    return order


@transaction.atomic
def update_order_status(order: Order, new_status: str, note: str = "", location: str = "") -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)

    if new_status == order.status:
        raise serializers.ValidationError(
            {"detail": f"Order {order.order_number} is already '{order.status}'."}
        )

    if not order.can_transition_to(new_status):
        raise serializers.ValidationError(
            {
                "detail": (
                    f"Cannot move order {order.order_number} from '{order.status}' to "
                    f"'{new_status}'."
                )
            }
        )

    if new_status == Order.Status.CANCELLED:
        return cancel_order(order, by_admin=True, reason=note or "Cancelled by store")

    order.status = new_status
    if new_status == Order.Status.DELIVERED:
        order.delivered_at = timezone.now()
        if order.payment_method == Order.PaymentMethod.COD:
            order.payment_status = Order.PaymentStatus.PAID
        order.save(
            update_fields=["status", "delivered_at", "payment_status", "updated_at"]
        )
    else:
        order.save(update_fields=["status", "updated_at"])

    defaults = {
        Order.Status.PACKED: "Seller packed your item",
        Order.Status.SHIPPED: "Handed over to the courier partner",
        Order.Status.OUT_FOR_DELIVERY: "Out for delivery in your area",
        Order.Status.DELIVERED: "Delivered - thanks for shopping with us",
    }
    log_event(order, new_status, note=note or defaults.get(new_status, ""), location=location)
    return order


def request_return(order: Order, user, *, reason: str, comment: str = "") -> ReturnRequest:
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if not order.is_returnable:
            raise serializers.ValidationError(
                {"detail": "This order is outside the 7 day return window or not delivered yet."}
            )
        open_return = order.returns.exclude(
            status__in=[ReturnRequest.Status.REJECTED, ReturnRequest.Status.REFUNDED]
        ).first()
        if open_return:
            raise serializers.ValidationError(
                {"detail": "A return request for this order is already in progress."}
            )

        request_obj = ReturnRequest.objects.create(
            order=order,
            user=user,
            reason=reason,
            comment=comment,
            refund_amount=order.total_amount,
        )
        order.status = Order.Status.RETURN_REQUESTED
        order.save(update_fields=["status", "updated_at"])
        log_event(order, Order.Status.RETURN_REQUESTED, note=f"Return requested: {reason}")
        return request_obj


@transaction.atomic
def resolve_return(return_request: ReturnRequest, *, action: str, admin_note: str = "") -> ReturnRequest:
    """action: approve | reject | refund"""
    return_request = ReturnRequest.objects.select_for_update().get(pk=return_request.pk)
    order = Order.objects.select_for_update().get(pk=return_request.order_id)

    if return_request.status in {ReturnRequest.Status.REJECTED, ReturnRequest.Status.REFUNDED}:
        raise serializers.ValidationError({"detail": "This return is already closed."})

    if action == "reject":
        return_request.status = ReturnRequest.Status.REJECTED
        return_request.admin_note = admin_note[:240]
        return_request.resolved_at = timezone.now()
        return_request.save(update_fields=["status", "admin_note", "resolved_at"])
        order.status = Order.Status.DELIVERED
        order.save(update_fields=["status", "updated_at"])
        log_event(order, Order.Status.DELIVERED, note="Return request rejected")
        return return_request

    if action == "approve":
        return_request.status = ReturnRequest.Status.APPROVED
        return_request.admin_note = admin_note[:240]
        return_request.save(update_fields=["status", "admin_note"])
        log_event(order, Order.Status.RETURN_REQUESTED, note="Return approved - pickup scheduled")
        return return_request

    if action == "refund":
        return_request.status = ReturnRequest.Status.REFUNDED
        return_request.admin_note = admin_note[:240]
        return_request.resolved_at = timezone.now()
        return_request.save(update_fields=["status", "admin_note", "resolved_at"])
        order.status = Order.Status.RETURNED
        order.payment_status = Order.PaymentStatus.REFUNDED
        order.save(update_fields=["status", "payment_status", "updated_at"])
        for item in order.items.all():
            Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)
        bump_catalog_version()  # restored stock must not stay stale in cache
        log_event(order, Order.Status.RETURNED, note="Refund processed to original payment method")
        return return_request

    raise serializers.ValidationError({"detail": f"Unknown return action '{action}'."})


# --------------------------------------------------------------------------
# Browsing helpers
# --------------------------------------------------------------------------


def record_view(user, product) -> None:
    if not user or not user.is_authenticated:
        return
    RecentlyViewed.objects.update_or_create(user=user, product=product)
    stale = list(
        RecentlyViewed.objects.filter(user=user).values_list("pk", flat=True)[30:]
    )
    if stale:
        RecentlyViewed.objects.filter(pk__in=stale).delete()
