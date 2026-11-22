"""Django admin registration for every store model."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import (
    Address,
    Brand,
    Cart,
    CartItem,
    Category,
    Coupon,
    Order,
    OrderEvent,
    OrderItem,
    Pincode,
    Product,
    ProductImage,
    RecentlyViewed,
    ReturnRequest,
    Review,
    User,
    WishlistItem,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "role", "phone", "is_active", "date_joined")
    list_filter = ("role", "is_active", "is_staff", "is_superuser")
    search_fields = ("username", "email", "first_name", "last_name", "phone")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Store profile", {"fields": ("role", "phone")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Store profile", {"fields": ("role", "email", "phone")}),
    )


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "label", "city", "pincode", "is_default")
    list_filter = ("label", "is_default", "state")
    search_fields = ("full_name", "user__username", "pincode", "city")
    list_select_related = ("user",)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "tagline", "is_active", "product_total")
    list_editable = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="Products")
    def product_total(self, obj):
        return obj.products.count()


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "icon", "position", "is_active", "product_total")
    list_editable = ("position", "is_active")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="Products")
    def product_total(self, obj):
        return obj.products.count()


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "brand",
        "category",
        "price",
        "mrp",
        "discount_tag",
        "stock",
        "rating",
        "is_active",
        "is_featured",
    )
    list_filter = ("is_active", "is_featured", "category", "brand", "cod_available")
    list_editable = ("price", "stock", "is_active", "is_featured")
    search_fields = ("name", "description", "sku", "brand__name")
    list_select_related = ("category", "brand")
    readonly_fields = ("created_at", "updated_at", "rating", "rating_count", "sold_count")
    inlines = [ProductImageInline]
    fieldsets = (
        ("Basics", {"fields": ("name", "slug", "brand", "category", "description", "highlights")}),
        ("Pricing", {"fields": ("mrp", "price")}),
        ("Inventory", {"fields": ("stock", "sku", "is_active", "is_featured", "badge")}),
        ("Media", {"fields": ("image_url",)}),
        ("Delivery", {"fields": ("delivery_days", "cod_available", "free_delivery", "return_days", "warranty")}),
        ("Signals", {"fields": ("rating", "rating_count", "sold_count", "created_at", "updated_at")}),
    )

    @admin.display(description="Discount")
    def discount_tag(self, obj):
        percent = obj.discount_percent
        if not percent:
            return "-"
        return format_html('<b style="color:#388e3c">{}% off</b>', percent)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "title", "is_verified_purchase", "created_at")
    list_filter = ("rating", "is_verified_purchase")
    search_fields = ("product__name", "user__username", "title", "body")
    list_select_related = ("product", "user")


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at")
    search_fields = ("user__username", "product__name")
    list_select_related = ("user", "product")


@admin.register(RecentlyViewed)
class RecentlyViewedAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "viewed_at")
    search_fields = ("user__username", "product__name")
    list_select_related = ("user", "product")


@admin.register(Pincode)
class PincodeAdmin(admin.ModelAdmin):
    list_display = ("pincode", "city", "state", "eta_min_days", "eta_max_days", "cod_available", "is_serviceable")
    list_filter = ("state", "cod_available", "is_serviceable")
    search_fields = ("pincode", "city", "state")


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_type", "value", "min_order_value", "used_count", "usage_limit", "live")
    list_filter = ("discount_type", "is_active")
    search_fields = ("code", "description")
    readonly_fields = ("used_count", "created_at")

    @admin.display(boolean=True, description="Live now")
    def live(self, obj):
        return obj.is_live


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    autocomplete_fields = ("product",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "coupon", "item_count", "subtotal", "updated_at")
    search_fields = ("user__username",)
    list_select_related = ("user", "coupon")
    inlines = [CartItemInline]

    @admin.display(description="Items")
    def item_count(self, obj):
        return obj.item_count

    @admin.display(description="Subtotal")
    def subtotal(self, obj):
        return obj.subtotal


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("id", "cart", "product", "quantity", "saved_for_later", "added_at")
    list_filter = ("saved_for_later",)
    search_fields = ("cart__user__username", "product__name")
    list_select_related = ("cart", "product")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "product_name", "unit_price", "unit_mrp", "quantity")

    def has_add_permission(self, request, obj=None):
        return False


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    readonly_fields = ("status", "note", "location", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


class ReturnRequestInline(admin.TabularInline):
    model = ReturnRequest
    extra = 0
    readonly_fields = ("reason", "status", "refund_amount", "admin_note", "created_at")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "user",
        "status",
        "payment_method",
        "payment_status",
        "total_amount",
        "created_at",
    )
    list_filter = ("status", "payment_method", "payment_status", "created_at")
    search_fields = ("order_number", "user__username", "shipping_phone", "shipping_name")
    list_select_related = ("user",)
    readonly_fields = (
        "order_number",
        "user",
        "subtotal",
        "discount_amount",
        "delivery_fee",
        "cod_fee",
        "gst_amount",
        "total_amount",
        "invoice_number",
        "created_at",
        "updated_at",
    )
    inlines = [OrderItemInline, OrderEventInline, ReturnRequestInline]
    date_hierarchy = "created_at"


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "product_name", "unit_price", "quantity", "line_total")
    search_fields = ("product_name", "order__order_number")
    list_select_related = ("order", "product")

    @admin.display(description="Line total")
    def line_total(self, obj):
        return obj.line_total


@admin.register(OrderEvent)
class OrderEventAdmin(admin.ModelAdmin):
    list_display = ("order", "status", "location", "created_at")
    list_filter = ("status",)
    search_fields = ("order__order_number", "note")
    list_select_related = ("order",)


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ("order", "user", "reason", "status", "refund_amount", "created_at")
    list_filter = ("status", "reason")
    search_fields = ("order__order_number", "user__username", "comment")
    list_select_related = ("order", "user")
