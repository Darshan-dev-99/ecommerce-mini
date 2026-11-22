"""Shopping cart: live quantity updates, save-for-later and coupons.

Every mutation returns the whole cart payload so the client can re-render
from one source of truth (no page reloads, no client-side price maths).
"""

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Cart, CartItem, Coupon, Order, Product, inr
from ..serializers import CartAddSerializer, CartSerializer, QuoteQuerySerializer
from ..services import CheckoutError, pincode_info, quote, validate_coupon


def get_cart(user) -> Cart:
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def cart_payload(cart: Cart, *, payment_method=Order.PaymentMethod.COD, pincode="") -> dict:
    """Serialise the cart plus a live price quote and delivery promise."""
    cart = (
        Cart.objects.select_related("coupon")
        .prefetch_related("items__product__brand")
        .get(pk=cart.pk)
    )
    data = CartSerializer(cart, context={"payment_method": payment_method}).data
    items = [item for item in cart.items.all() if not item.saved_for_later]
    products = [item.product for item in items]
    serviceable = pincode_info(pincode) if pincode else None
    if serviceable:
        data["delivery"] = {
            "pincode": serviceable.pincode,
            "city": serviceable.city,
            "state": serviceable.state,
            "eta_min_days": serviceable.eta_min_days,
            "eta_max_days": serviceable.eta_max_days,
            "cod_available": serviceable.cod_available,
        }
    data["free_delivery_threshold"] = int(settings.STORE["free_delivery_threshold"])
    data["payment_method"] = payment_method
    data["issues"] = [
        {
            "item": item.pk,
            "product": item.product.name,
            "message": (
                f"{item.product.name} is out of stock."
                if item.product.stock == 0
                else f"Only {item.product.stock} left of {item.product.name}."
            ),
        }
        for item in items
        if not item.product.is_active or item.product.stock < item.quantity
    ]
    data["stock_ok"] = not data["issues"]
    return data


def resolve_payment(request) -> str:
    method = (
        request.data.get("payment_method")
        if hasattr(request, "data") and isinstance(request.data, dict)
        else None
    ) or request.query_params.get("payment_method") or request.session.get("payment_method")
    allowed = {choice for choice, _ in Order.PaymentMethod.choices}
    if method not in allowed:
        method = Order.PaymentMethod.COD
    request.session["payment_method"] = method
    return method


class CartView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart = get_cart(request.user)
        return Response(
            cart_payload(
                cart,
                payment_method=resolve_payment(request),
                pincode=(request.query_params.get("pincode") or "").strip(),
            )
        )

    def delete(self, request):
        cart = get_cart(request.user)
        cart.items.all().delete()
        cart.coupon = None
        cart.save(update_fields=["coupon", "updated_at"])
        return Response(cart_payload(cart))


class CartItemView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Add a product, or bump the quantity if it is already in the cart."""
        serializer = CartAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = get_object_or_404(Product, pk=serializer.validated_data["product"])
        quantity = serializer.validated_data["quantity"]
        cart = get_cart(request.user)

        if not product.is_active:
            raise ValidationError({"detail": f"{product.name} is no longer available."})
        if product.stock <= 0:
            raise ValidationError({"detail": f"{product.name} is out of stock."})

        with transaction.atomic():
            item, created = CartItem.objects.select_for_update().get_or_create(
                cart=cart, product=product, defaults={"quantity": quantity}
            )
            target = quantity if created else item.quantity + quantity
            if target > product.stock:
                raise ValidationError(
                    {
                        "detail": (
                            f"Only {product.stock} unit(s) of {product.name} are in stock."
                        )
                    }
                )
            if not created:
                item.quantity = target
                item.saved_for_later = False
                item.save(update_fields=["quantity", "saved_for_later"])

        return Response(
            {
                "added": True,
                "message": f"{product.name} added to cart.",
                "cart": cart_payload(cart, payment_method=resolve_payment(request)),
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def patch(self, request, pk):
        cart = get_cart(request.user)
        item = get_object_or_404(CartItem, pk=pk, cart=cart)
        product = item.product

        if "saved_for_later" in request.data:
            save_later = bool(request.data.get("saved_for_later"))
            if not save_later and product.stock < item.quantity:
                raise ValidationError(
                    {"detail": f"Only {product.stock} unit(s) of {product.name} are in stock."}
                )
            item.saved_for_later = save_later
            item.save(update_fields=["saved_for_later"])
            message = (
                "Moved to saved for later." if save_later else "Moved back to your cart."
            )
            return Response(
                {"message": message, "cart": cart_payload(cart, payment_method=resolve_payment(request))}
            )

        try:
            quantity = int(request.data.get("quantity"))
        except (TypeError, ValueError):
            raise ValidationError({"quantity": "Quantity must be a whole number."})

        if quantity < 1:
            raise ValidationError({"quantity": "Quantity must be at least 1."})
        if quantity > product.stock:
            raise ValidationError(
                {"detail": f"Only {product.stock} unit(s) of {product.name} are in stock."}
            )

        item.quantity = quantity
        item.save(update_fields=["quantity"])
        return Response(
            {"message": "Cart updated.", "cart": cart_payload(cart, payment_method=resolve_payment(request))}
        )

    def delete(self, request, pk):
        cart = get_cart(request.user)
        item = get_object_or_404(CartItem, pk=pk, cart=cart)
        name = item.product.name
        item.delete()
        return Response(
            {
                "message": f"{name} removed from cart.",
                "cart": cart_payload(cart, payment_method=resolve_payment(request)),
            }
        )


class CartCouponView(APIView):
    """Apply or remove a coupon on the signed-in user's cart."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        cart = get_cart(request.user)
        code = (request.data.get("code") or "").strip()
        subtotal = cart.subtotal
        if subtotal <= 0:
            raise CheckoutError({"detail": "Add something to your cart first."})

        coupon, discount = validate_coupon(code, request.user, subtotal, cart=cart)
        cart.coupon = coupon
        cart.save(update_fields=["coupon", "updated_at"])
        return Response(
            {
                "message": f"Coupon {coupon.code} applied - you saved \u20b9{discount}.",
                "saved": str(inr(discount)),
                "cart": cart_payload(cart, payment_method=resolve_payment(request)),
            }
        )

    def delete(self, request):
        cart = get_cart(request.user)
        cart.coupon = None
        cart.save(update_fields=["coupon", "updated_at"])
        return Response(
            {
                "message": "Coupon removed.",
                "cart": cart_payload(cart, payment_method=resolve_payment(request)),
            }
        )


class CartQuoteView(APIView):
    """Pre-checkout price preview: items + coupon + payment + pincode."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = QuoteQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = get_cart(request.user)
        items = [item for item in cart.items.all() if not item.saved_for_later]
        if not items:
            raise ValidationError({"detail": "Your cart is empty."})

        products = [item.product for item in items]
        subtotal = inr(sum((item.subtotal for item in items), inr(0)))
        payment = serializer.validated_data["payment_method"]
        pincode = serializer.validated_data.get("pincode", "")

        coupon = None
        code = (serializer.validated_data.get("coupon_code") or "").strip()
        if code:
            coupon, _ = validate_coupon(code, request.user, subtotal, cart=cart)
        elif cart.coupon_id:
            coupon = cart.coupon

        totals = quote(subtotal, coupon=coupon, payment_method=payment, products=products)
        serviceable = pincode_info(pincode) if pincode else None
        return Response(
            {
                **totals,
                "payment_method": payment,
                "coupon_code": coupon.code if coupon else "",
                "free_delivery_threshold": int(settings.STORE["free_delivery_threshold"]),
                "cod_available": (
                    payment != Order.PaymentMethod.COD
                    or (serviceable.cod_available if serviceable else True)
                ),
                "delivery": (
                    {
                        "pincode": serviceable.pincode,
                        "city": serviceable.city,
                        "eta_min_days": serviceable.eta_min_days,
                        "eta_max_days": serviceable.eta_max_days,
                    }
                    if serviceable
                    else None
                ),
                "coupon": (
                    {
                        "code": coupon.code,
                        "description": coupon.description,
                    }
                    if coupon
                    else None
                ),
            }
        )


class CouponStripView(APIView):
    """Live coupons shown on the cart and checkout pages."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart = get_cart(request.user)
        subtotal = cart.subtotal
        rows = Coupon.objects.filter(is_active=True).order_by("-value")[:12]
        return Response(
            {
                "subtotal": subtotal,
                "results": [
                    {
                        "code": coupon.code,
                        "description": coupon.description,
                        "min_order_value": coupon.min_order_value,
                        "max_discount": coupon.max_discount,
                        "discount_type": coupon.discount_type,
                        "value": coupon.value,
                        "preview": str(coupon.discount_for(subtotal or coupon.min_order_value)),
                        "eligible": subtotal >= coupon.min_order_value and coupon.is_live,
                        "shortfall": str(
                            inr(max(0, coupon.min_order_value - subtotal))
                        ),
                    }
                    for coupon in rows
                    if coupon.is_live
                ],
            }
        )
