"""Commerce serializers: cart, coupons, checkout, orders and returns."""

from django.conf import settings
from rest_framework import serializers

from ..models import (
    Address,
    Cart,
    CartItem,
    Coupon,
    Order,
    OrderEvent,
    OrderItem,
    ReturnRequest,
    inr,
)
from ..services import quote

STORE = settings.STORE


class CartProductSerializer(serializers.Serializer):
    """Lightweight product projection embedded in cart lines."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.CharField()
    brand_name = serializers.SerializerMethodField()
    image_url = serializers.CharField(allow_blank=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    mrp = serializers.DecimalField(max_digits=10, decimal_places=2)
    stock = serializers.IntegerField()
    is_active = serializers.BooleanField()
    delivery_days = serializers.IntegerField()

    def get_brand_name(self, obj):
        return obj.brand.name if obj.brand_id else ""


class CartItemSerializer(serializers.ModelSerializer):
    product_detail = CartProductSerializer(source="product", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    image_url = serializers.CharField(source="product.image_url", read_only=True)
    slug = serializers.CharField(source="product.slug", read_only=True)
    unit_price = serializers.DecimalField(source="product.price", max_digits=10, decimal_places=2, read_only=True)
    unit_mrp = serializers.DecimalField(source="product.mrp", max_digits=10, decimal_places=2, read_only=True)
    stock = serializers.IntegerField(source="product.stock", read_only=True)
    is_active = serializers.BooleanField(source="product.is_active", read_only=True)
    max_quantity = serializers.IntegerField(source="product.stock", read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = [
            "id",
            "product",
            "product_detail",
            "product_name",
            "image_url",
            "slug",
            "unit_price",
            "unit_mrp",
            "quantity",
            "stock",
            "max_quantity",
            "is_active",
            "subtotal",
            "saved_for_later",
            "added_at",
        ]
        read_only_fields = ["id", "added_at"]


class AppliedCouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = ["code", "description", "discount_type", "value", "min_order_value", "max_discount"]


class CartSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    saved_items = serializers.SerializerMethodField()
    item_count = serializers.IntegerField(read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    coupon = AppliedCouponSerializer(read_only=True)
    summary = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ["id", "items", "saved_items", "item_count", "subtotal", "coupon", "summary", "updated_at"]

    def get_items(self, obj):
        active = [item for item in obj.items.all() if not item.saved_for_later]
        return CartItemSerializer(active, many=True).data

    def get_saved_items(self, obj):
        saved = [item for item in obj.items.all() if item.saved_for_later]
        return CartItemSerializer(saved, many=True).data

    def get_summary(self, obj):
        payment = self.context.get("payment_method", Order.PaymentMethod.COD)
        products = [item.product for item in obj.items.all() if not item.saved_for_later]
        return quote(obj.subtotal, coupon=obj.coupon, payment_method=payment, products=products)


class CouponSerializer(serializers.ModelSerializer):
    is_live = serializers.BooleanField(read_only=True)
    discount_for_sample = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = [
            "id",
            "code",
            "description",
            "discount_type",
            "value",
            "min_order_value",
            "max_discount",
            "valid_from",
            "valid_to",
            "usage_limit",
            "used_count",
            "per_user_limit",
            "is_active",
            "is_live",
            "discount_for_sample",
            "created_at",
        ]
        read_only_fields = ["id", "used_count", "created_at"]

    def get_discount_for_sample(self, obj):
        return str(obj.discount_for(2000))

    def validate_code(self, value):
        value = (value or "").strip().upper()
        if not value.isalnum():
            raise serializers.ValidationError("Use letters and numbers only.")
        qs = Coupon.objects.filter(code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A coupon with that code already exists.")
        return value

    def validate(self, attrs):
        start = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        end = attrs.get("valid_to", getattr(self.instance, "valid_to", None))
        if end and start and end <= start:
            raise serializers.ValidationError({"valid_to": "End date must be after the start date."})
        if attrs.get("discount_type") == Coupon.DiscountType.PERCENT:
            value = attrs.get("value", getattr(self.instance, "value", 0))
            if value and value > 90:
                raise serializers.ValidationError({"value": "Percentage discounts are capped at 90%."})
        return attrs


class OrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    line_saving = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    slug = serializers.CharField(source="product.slug", read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "slug",
            "product_name",
            "product_brand",
            "image_url",
            "unit_price",
            "unit_mrp",
            "quantity",
            "line_total",
            "line_saving",
        ]


class OrderEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderEvent
        fields = ["id", "status", "note", "location", "created_at"]


class ReturnRequestSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)

    class Meta:
        model = ReturnRequest
        fields = [
            "id",
            "order",
            "order_number",
            "reason",
            "reason_display",
            "comment",
            "status",
            "refund_amount",
            "admin_note",
            "created_at",
            "resolved_at",
        ]
        read_only_fields = ["id", "order", "status", "refund_amount", "admin_note", "created_at", "resolved_at"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    events = OrderEventSerializer(many=True, read_only=True)
    returns = ReturnRequestSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    payment_method_display = serializers.CharField(source="get_payment_method_display", read_only=True)
    is_cancellable = serializers.BooleanField(read_only=True)
    is_returnable = serializers.BooleanField(read_only=True)
    next_statuses = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()
    full_address = serializers.CharField(read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "customer",
            "status",
            "status_display",
            "payment_method",
            "payment_method_display",
            "payment_status",
            "payment_reference",
            "coupon_code",
            "subtotal",
            "discount_amount",
            "delivery_fee",
            "cod_fee",
            "gst_amount",
            "total_amount",
            "items",
            "item_count",
            "events",
            "returns",
            "shipping_name",
            "shipping_phone",
            "full_address",
            "shipping_pincode",
            "invoice_number",
            "delivery_eta",
            "cancel_reason",
            "is_cancellable",
            "is_returnable",
            "next_statuses",
            "created_at",
            "updated_at",
            "delivered_at",
        ]

    def get_next_statuses(self, obj):
        return Order.ALLOWED_TRANSITIONS.get(obj.status, [])

    def get_item_count(self, obj):
        return sum(item.quantity for item in obj.items.all())

    def get_customer(self, obj):
        return {
            "id": obj.user_id,
            "username": obj.user.username,
            "display_name": obj.user.get_full_name() or obj.user.username,
        }


class PlaceOrderSerializer(serializers.Serializer):
    address_id = serializers.IntegerField(required=False)
    payment_method = serializers.ChoiceField(choices=Order.PaymentMethod.choices)
    coupon_code = serializers.CharField(required=False, allow_blank=True)
    shipping_address = serializers.CharField(required=False, allow_blank=True, help_text="Legacy free-text fallback")

    #: Populated in validate() for the view to consume.
    address = None

    def validate(self, attrs):
        user = self.context["user"]
        address_id = attrs.get("address_id")
        if address_id:
            address = Address.objects.filter(pk=address_id, user=user).first()
            if not address:
                raise serializers.ValidationError({"address_id": "Select a saved delivery address."})
        else:
            legacy = (attrs.get("shipping_address") or "").strip()
            if len(legacy) < 10:
                raise serializers.ValidationError(
                    {"address_id": "Add a delivery address before placing the order."}
                )
            pincode = legacy.split()[-1] if legacy.split() else ""
            address = Address(
                user=user,
                label="Other",
                full_name=user.get_full_name() or user.username,
                phone=user.phone or "9999999999",
                line1=legacy[:200],
                city="",
                state="",
                pincode=pincode if pincode.isdigit() and len(pincode) == 6 else "560001",
            )
        attrs["address"] = address
        return attrs


class ReturnRequestCreateSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=ReturnRequest.Reason.choices)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class QuoteQuerySerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(choices=Order.PaymentMethod.choices, default=Order.PaymentMethod.COD)
    coupon_code = serializers.CharField(required=False, allow_blank=True)
    pincode = serializers.CharField(required=False, allow_blank=True)


class CartAddSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)


def money(value):
    return str(inr(value))
