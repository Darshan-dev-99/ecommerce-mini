"""Catalog serializers: brands, categories, products, reviews, pincodes."""

from decimal import Decimal

from django.db.models import Count
from rest_framework import serializers

from ..models import Brand, Category, Pincode, Product, ProductImage, Review


class BrandSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = Brand
        fields = ["id", "name", "slug", "tagline", "logo_url", "is_active", "product_count"]
        read_only_fields = ["id", "slug"]


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "icon",
            "image_url",
            "position",
            "is_active",
            "product_count",
        ]
        read_only_fields = ["id", "slug"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Category name cannot be blank.")
        qs = Category.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A category with that name exists.")
        return value


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "url", "alt", "position"]


class ProductListSerializer(serializers.ModelSerializer):
    """Card-sized payload used by grids, rails and search results."""

    brand_name = serializers.CharField(source="brand.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)
    saving = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "brand_name",
            "category",
            "category_name",
            "category_slug",
            "price",
            "mrp",
            "discount_percent",
            "saving",
            "rating",
            "rating_count",
            "stock",
            "in_stock",
            "image_url",
            "badge",
            "is_featured",
            "is_active",
            "free_delivery",
            "delivery_days",
            "cod_available",
            "sold_count",
        ]


class ProductDetailSerializer(ProductListSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    gst_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    rating_breakdown = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            "description",
            "highlights",
            "images",
            "gst_amount",
            "sku",
            "warranty",
            "return_days",
            "is_active",
            "rating_breakdown",
            "created_at",
            "updated_at",
        ]

    def get_rating_breakdown(self, obj):
        rows = obj.reviews.values("rating").annotate(count=Count("id"))
        counts = {row["rating"]: row["count"] for row in rows}
        total = obj.rating_count or 0
        return {
            str(star): {
                "count": counts.get(star, 0),
                "percent": round(counts.get(star, 0) / total * 100) if total else 0,
            }
            for star in range(5, 0, -1)
        }


class ProductWriteSerializer(serializers.ModelSerializer):
    """Admin create/update payload with the catalog validation rules."""

    images = ProductImageSerializer(many=True, read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    image_urls = serializers.ListField(
        child=serializers.URLField(max_length=500), write_only=True, required=False
    )
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    mrp = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01"), required=False
    )
    in_stock = serializers.BooleanField(read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "brand",
            "brand_name",
            "category",
            "category_name",
            "description",
            "highlights",
            "price",
            "mrp",
            "stock",
            "sku",
            "image_url",
            "image_urls",
            "images",
            "is_active",
            "is_featured",
            "badge",
            "delivery_days",
            "cod_available",
            "free_delivery",
            "return_days",
            "warranty",
            "in_stock",
            "discount_percent",
            "rating",
            "rating_count",
            "sold_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "rating", "rating_count", "sold_count", "created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Product name cannot be blank.")
        return value

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than zero.")
        return value

    def validate_stock(self, value):
        if value < 0:
            raise serializers.ValidationError("Stock cannot be negative.")
        return value

    def validate_highlights(self, value):
        if isinstance(value, str):
            value = [line.strip() for line in value.splitlines() if line.strip()]
        if not isinstance(value, list):
            raise serializers.ValidationError("Highlights must be a list of bullet points.")
        return [str(item)[:200] for item in value][:10]

    def validate(self, attrs):
        price = attrs.get("price", getattr(self.instance, "price", None))
        if price is None:
            raise serializers.ValidationError({"price": "A selling price is required."})
        mrp = attrs.get("mrp", getattr(self.instance, "mrp", None))
        if mrp is None:
            # MRP is optional at the API level: default it to the selling price.
            attrs["mrp"] = price
            mrp = price
        if mrp < price:
            raise serializers.ValidationError(
                {"mrp": "MRP must be greater than or equal to the selling price."}
            )
        return attrs

    def _sync_images(self, product, urls):
        if urls is None:
            return
        product.images.all().delete()
        ProductImage.objects.bulk_create(
            [
                ProductImage(product=product, url=url, alt=product.name, position=index)
                for index, url in enumerate(urls[:6])
            ]
        )
        if urls and not product.image_url:
            product.image_url = urls[0]
            product.save(update_fields=["image_url"])

    def create(self, validated_data):
        urls = validated_data.pop("image_urls", None)
        if not validated_data.get("mrp"):
            validated_data["mrp"] = validated_data["price"]
        if not validated_data.get("image_url") and urls:
            validated_data["image_url"] = urls[0]
        product = Product.objects.create(**validated_data)
        self._sync_images(product, urls)
        return product

    def update(self, instance, validated_data):
        urls = validated_data.pop("image_urls", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if instance.mrp < instance.price:
            instance.mrp = instance.price
        instance.save()
        self._sync_images(instance, urls)
        return instance


class ReviewSerializer(serializers.ModelSerializer):
    user_display = serializers.SerializerMethodField()
    rating = serializers.IntegerField(min_value=1, max_value=5)

    class Meta:
        model = Review
        fields = [
            "id",
            "product",
            "rating",
            "title",
            "body",
            "user_display",
            "is_verified_purchase",
            "created_at",
        ]
        read_only_fields = ["id", "product", "user_display", "is_verified_purchase", "created_at"]

    def get_user_display(self, obj):
        name = obj.user.get_full_name() or obj.user.username
        return f"{name[:1]}***{name[-1:]}".upper() if len(name) > 2 else name

    def validate_title(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("Give your review a short title.")
        return value

    def validate_body(self, value):
        value = value.strip()
        if len(value) < 10:
            raise serializers.ValidationError("Please write at least 10 characters.")
        return value


class PincodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pincode
        fields = ["pincode", "city", "state", "eta_min_days", "eta_max_days", "cod_available", "is_serviceable"]
