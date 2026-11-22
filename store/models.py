"""Domain models for the BazaarNoon marketplace.

The catalog is India-first: prices in INR, MRP vs selling price, GST-inclusive
totals, pincode serviceability, COD and UPI payments.
"""

import random
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

STORE = getattr(settings, "STORE", {})
GST_RATE = Decimal(str(STORE.get("gst_rate", "0.18")))


def inr(value) -> Decimal:
    """Quantise any money value to paise."""
    return Decimal(value or 0).quantize(Decimal("0.01"))


class Role(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    ADMIN = "admin", "Store Manager"


# --------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    phone = models.CharField(max_length=15, blank=True)

    @property
    def is_store_admin(self) -> bool:
        return self.role == Role.ADMIN or self.is_superuser

    def save(self, *args, **kwargs):
        if self.role == Role.ADMIN:
            self.is_staff = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class Address(models.Model):
    """Saved delivery address - Indian addresses are pincode centric."""

    LABELS = [("Home", "Home"), ("Work", "Work"), ("Other", "Other")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=20, choices=LABELS, default="Home")
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=15)
    line1 = models.CharField(max_length=200)
    line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    pincode = models.CharField(max_length=6)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]
        verbose_name_plural = "addresses"

    @property
    def formatted(self) -> str:
        parts = [self.line1, self.line2, self.city, self.state, self.pincode]
        return ", ".join(part for part in parts if part)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            Address.objects.filter(user=self.user).exclude(pk=self.pk).update(is_default=False)

    def __str__(self):
        return f"{self.label} - {self.city} {self.pincode}"


# --------------------------------------------------------------------------
# Catalog
# --------------------------------------------------------------------------


class Brand(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    tagline = models.CharField(max_length=160, blank=True)
    logo_url = models.URLField(max_length=400, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=16, blank=True, help_text="Emoji used in the nav rail")
    image_url = models.URLField(max_length=400, blank=True)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "name"]
        verbose_name_plural = "categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="products", null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    description = models.TextField(blank=True)
    highlights = models.JSONField(default=list, blank=True, help_text="Bullet points shown on the product page")

    mrp = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Maximum retail price (strike-through price)",
    )
    price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )

    stock = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    sku = models.CharField(max_length=40, blank=True, db_index=True)
    image_url = models.URLField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    badge = models.CharField(max_length=24, blank=True, help_text="e.g. Bestseller, Deal of the Day")

    rating = models.DecimalField(max_digits=2, decimal_places=1, default=Decimal("0.0"))
    rating_count = models.PositiveIntegerField(default=0)
    review_count = models.PositiveIntegerField(default=0)
    sold_count = models.PositiveIntegerField(default=0)

    delivery_days = models.PositiveSmallIntegerField(default=3)
    cod_available = models.BooleanField(default=True)
    free_delivery = models.BooleanField(default=False)
    return_days = models.PositiveSmallIntegerField(default=7)
    warranty = models.CharField(max_length=80, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["is_active", "-created_at"]),
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["brand", "is_active"]),
            models.Index(fields=["price"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gt=0), name="product_price_positive"),
            models.CheckConstraint(condition=models.Q(mrp__gte=models.F("price")), name="product_mrp_gte_price"),
            models.CheckConstraint(condition=models.Q(stock__gte=0), name="product_stock_non_negative"),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(f"{self.name}-{self.brand.name if self.brand_id else ''}")[:200] or "product"
            candidate, index = base, 2
            while Product.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base}-{index}"
                index += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    @property
    def in_stock(self) -> bool:
        return self.stock > 0

    @property
    def discount_percent(self) -> int:
        if self.mrp and self.mrp > 0 and self.price < self.mrp:
            return int(round((self.mrp - self.price) / self.mrp * 100))
        return 0

    @property
    def saving(self) -> Decimal:
        return inr(max(Decimal("0.00"), self.mrp - self.price))

    @property
    def gst_amount(self) -> Decimal:
        """GST component already included in the selling price."""
        return inr(self.price - (self.price / (1 + GST_RATE)))

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    url = models.URLField(max_length=500)
    alt = models.CharField(max_length=160, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.product.name} image {self.position}"


class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=140)
    body = models.TextField()
    is_verified_purchase = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["product", "user"], name="one_review_per_user_product")
        ]

    def __str__(self):
        return f"{self.rating}★ {self.product.name} by {self.user.username}"


class WishlistItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wishlist")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="unique_wishlist_item")
        ]

    def __str__(self):
        return f"{self.user.username} ♥ {self.product.name}"


class RecentlyViewed(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recent_views")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="recent_views")
    viewed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-viewed_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="unique_recent_view")
        ]

    def __str__(self):
        return f"{self.user.username} viewed {self.product.name}"


class Pincode(models.Model):
    """Serviceability, COD eligibility and delivery ETA per Indian pincode."""

    pincode = models.CharField(max_length=6, unique=True)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    eta_min_days = models.PositiveSmallIntegerField(default=2)
    eta_max_days = models.PositiveSmallIntegerField(default=4)
    cod_available = models.BooleanField(default=True)
    is_serviceable = models.BooleanField(default=True)

    class Meta:
        ordering = ["pincode"]
        verbose_name_plural = "pincodes"

    def __str__(self):
        return f"{self.pincode} ({self.city})"


# --------------------------------------------------------------------------
# Promotions
# --------------------------------------------------------------------------


class Coupon(models.Model):
    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Percentage"
        FLAT = "flat", "Flat amount"

    code = models.CharField(max_length=24, unique=True)
    description = models.CharField(max_length=200, blank=True)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices, default=DiscountType.PERCENT)
    value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("1"))])
    min_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(default=0, help_text="0 means unlimited")
    used_count = models.PositiveIntegerField(default=0)
    per_user_limit = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def is_live(self) -> bool:
        now = timezone.now()
        if not self.is_active:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_to and now > self.valid_to:
            return False
        if self.usage_limit and self.used_count >= self.usage_limit:
            return False
        return True

    def discount_for(self, subtotal) -> Decimal:
        subtotal = inr(subtotal)
        if subtotal < self.min_order_value:
            return Decimal("0.00")
        if self.discount_type == self.DiscountType.PERCENT:
            amount = subtotal * self.value / Decimal("100")
        else:
            amount = self.value
        if self.max_discount:
            amount = min(amount, self.max_discount)
        return inr(min(amount, subtotal))

    def __str__(self):
        return f"{self.code} ({self.get_discount_type_display()} {self.value})"


# --------------------------------------------------------------------------
# Cart
# --------------------------------------------------------------------------


class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="cart")
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name="carts")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def active_items(self):
        return [item for item in self.items.all() if not item.saved_for_later]

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.active_items)

    @property
    def subtotal(self) -> Decimal:
        return inr(sum((item.subtotal for item in self.active_items), Decimal("0.00")))

    @property
    def total(self) -> Decimal:
        return self.subtotal

    def __str__(self):
        return f"Cart of {self.user.username}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    saved_for_later = models.BooleanField(default=False)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_at"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "product"], name="unique_product_per_cart"),
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name="cart_item_quantity_positive"),
        ]

    @property
    def subtotal(self) -> Decimal:
        return inr(self.product.price * self.quantity)

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"


# --------------------------------------------------------------------------
# Orders
# --------------------------------------------------------------------------


class Order(models.Model):
    class Status(models.TextChoices):
        PLACED = "Placed", "Placed"
        PACKED = "Packed", "Packed"
        SHIPPED = "Shipped", "Shipped"
        OUT_FOR_DELIVERY = "Out for delivery", "Out for delivery"
        DELIVERED = "Delivered", "Delivered"
        CANCELLED = "Cancelled", "Cancelled"
        RETURN_REQUESTED = "Return requested", "Return requested"
        RETURNED = "Returned", "Returned"

    class PaymentMethod(models.TextChoices):
        COD = "COD", "Cash on Delivery"
        UPI = "UPI", "UPI"
        CARD = "Card", "Credit / Debit Card"
        NETBANKING = "NetBanking", "Net Banking"
        EMI = "EMI", "EMI"

    class PaymentStatus(models.TextChoices):
        PENDING = "Pending", "Pending"
        PAID = "Paid", "Paid"
        REFUNDED = "Refunded", "Refunded"
        FAILED = "Failed", "Failed"

    ALLOWED_TRANSITIONS = {
        Status.PLACED: [Status.PACKED, Status.CANCELLED],
        Status.PACKED: [Status.SHIPPED, Status.CANCELLED],
        Status.SHIPPED: [Status.OUT_FOR_DELIVERY],
        Status.OUT_FOR_DELIVERY: [Status.DELIVERED],
        Status.DELIVERED: [Status.RETURN_REQUESTED],
        Status.RETURN_REQUESTED: [Status.RETURNED, Status.DELIVERED],
        Status.CANCELLED: [],
        Status.RETURNED: [],
    }

    order_number = models.CharField(max_length=24, unique=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PLACED)

    payment_method = models.CharField(max_length=16, choices=PaymentMethod.choices, default=PaymentMethod.COD)
    payment_status = models.CharField(max_length=12, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    payment_reference = models.CharField(max_length=64, blank=True)

    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    coupon_code = models.CharField(max_length=24, blank=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cod_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    shipping_name = models.CharField(max_length=120)
    shipping_phone = models.CharField(max_length=15)
    shipping_line1 = models.CharField(max_length=200)
    shipping_line2 = models.CharField(max_length=200, blank=True)
    shipping_city = models.CharField(max_length=80)
    shipping_state = models.CharField(max_length=80)
    shipping_pincode = models.CharField(max_length=6)

    invoice_number = models.CharField(max_length=32, blank=True)
    delivery_eta = models.DateField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def save(self, *args, **kwargs):
        if not self.order_number:
            prefix = timezone.localtime().strftime("BN%Y%m%d")
            self.order_number = f"{prefix}{random.randint(1000, 9999)}"
            while Order.objects.filter(order_number=self.order_number).exists():
                self.order_number = f"{prefix}{random.randint(1000, 9999)}"
        super().save(*args, **kwargs)

    # -- state helpers -----------------------------------------------------
    @property
    def is_cancellable(self) -> bool:
        return self.status in {self.Status.PLACED, self.Status.PACKED}

    @property
    def is_returnable(self) -> bool:
        if self.status != self.Status.DELIVERED or not self.delivered_at:
            return False
        return (timezone.now() - self.delivered_at).days <= 7

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in self.ALLOWED_TRANSITIONS.get(self.status, [])

    @property
    def total_savings(self) -> Decimal:
        return inr(self.discount_amount)

    @property
    def full_address(self) -> str:
        parts = [
            self.shipping_line1,
            self.shipping_line2,
            self.shipping_city,
            self.shipping_state,
            self.shipping_pincode,
        ]
        return ", ".join(part for part in parts if part)

    def __str__(self):
        return f"{self.order_number} - {self.user.username} - {self.status}"


class OrderItem(models.Model):
    """A line on an order with price, MRP and name snapshotted at purchase."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    product_name = models.CharField(max_length=200)
    product_brand = models.CharField(max_length=80, blank=True)
    image_url = models.CharField(max_length=500, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    unit_mrp = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField()

    class Meta:
        ordering = ["id"]

    @property
    def line_total(self) -> Decimal:
        return inr(self.unit_price * self.quantity)

    @property
    def line_saving(self) -> Decimal:
        return inr(max(Decimal("0.00"), (self.unit_mrp - self.unit_price) * self.quantity))

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"


class OrderEvent(models.Model):
    """Tracking timeline entry (visible to the customer)."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=32)
    note = models.CharField(max_length=240, blank=True)
    location = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.order.order_number} -> {self.status}"


class ReturnRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "Requested", "Requested"
        APPROVED = "Approved", "Approved"
        REJECTED = "Rejected", "Rejected"
        REFUNDED = "Refunded", "Refunded"

    class Reason(models.TextChoices):
        DAMAGED = "Damaged", "Item arrived damaged"
        WRONG_ITEM = "Wrong item", "Wrong item delivered"
        NOT_AS_DESCRIBED = "Not as described", "Not as described"
        CHANGED_MIND = "Changed mind", "Changed my mind"
        OTHER = "Other", "Other"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="returns")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="returns")
    reason = models.CharField(max_length=24, choices=Reason.choices)
    comment = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REQUESTED)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    admin_note = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Return for {self.order.order_number} ({self.status})"
