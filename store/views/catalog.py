"""Catalog endpoints: products, categories, brands, reviews, search, wishlist.

Read paths are cache-aside: the API checks the cache first, and only a miss
touches the database before backfilling the cache.
"""

from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db.models import Case, Count, ExpressionWrapper, F, FloatField, Q, Value, When
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated, NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..cache import cache_aside
from ..models import (
    Brand,
    Category,
    Coupon,
    Order,
    Product,
    RecentlyViewed,
    Review,
    WishlistItem,
)
from ..permissions import IsAdminOrReadOnly, IsStoreAdmin, is_store_admin
from ..serializers import (
    BrandSerializer,
    CategorySerializer,
    PincodeSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ProductWriteSerializer,
    ReviewSerializer,
)
from ..services import pincode_info, record_view

TTL = settings.CACHE_TTL

DISCOUNT_RATIO = ExpressionWrapper(
    (F("mrp") - F("price")) * Value(1.0) / F("mrp"), output_field=FloatField()
)

ORDERINGS = {
    "relevance": ("search_rank", "-sold_count"),
    "price": ("price", "id"),
    "-price": ("-price", "id"),
    "rating": ("-rating", "-rating_count"),
    "-rating": ("rating", "id"),
    "newest": ("-created_at", "-id"),
    "popularity": ("-sold_count", "-rating"),
    "discount": ("-discount_ratio", "price"),
    "name": ("name",),
    "-name": ("-name",),
}


def parse_decimal(raw, label):
    if raw in (None, "", "null"):
        return None
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValidationError({"detail": f"{label} must be a number."})


def normalise_params(params, *, admin: bool) -> dict:
    """Whitelist query params so the cache key is stable and small."""
    clean = {
        "search": (params.get("search") or "").strip()[:80],
        "category": (params.get("category") or "all").strip()[:60],
        "brand": (params.get("brand") or "").strip()[:200],
        "min_price": parse_decimal(params.get("min_price"), "Minimum price"),
        "max_price": parse_decimal(params.get("max_price"), "Maximum price"),
        "min_rating": parse_decimal(params.get("min_rating"), "Minimum rating"),
        "min_discount": parse_decimal(params.get("min_discount"), "Minimum discount"),
        "in_stock": params.get("in_stock") in {"1", "true", "yes"},
        "ordering": params.get("ordering") or "relevance",
        "page": max(1, int(params.get("page") or 1)),
        "page_size": min(60, max(4, int(params.get("page_size") or 24))),
        "admin": bool(admin and params.get("include_inactive") in {"1", "true", "yes"}),
    }
    if clean["ordering"] not in ORDERINGS:
        clean["ordering"] = "relevance"
    return clean


def build_product_queryset(params: dict):
    qs = Product.objects.select_related("brand", "category").annotate(discount_ratio=DISCOUNT_RATIO)

    if not params["admin"]:
        qs = qs.filter(is_active=True)

    category = params["category"]
    if category and category != "all":
        if category.isdigit():
            qs = qs.filter(category_id=int(category))
        else:
            qs = qs.filter(category__slug=category)

    brand = params["brand"]
    if brand:
        tokens = [token for token in brand.split(",") if token]
        by_id = [int(t) for t in tokens if t.isdigit()]
        by_slug = [t for t in tokens if not t.isdigit()]
        condition = Q(pk__in=[])
        if by_id:
            condition |= Q(brand_id__in=by_id)
        if by_slug:
            condition |= Q(brand__slug__in=by_slug)
        qs = qs.filter(condition)

    search = params["search"]
    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(description__icontains=search)
            | Q(brand__name__icontains=search)
            | Q(category__name__icontains=search)
        )
        qs = qs.annotate(
            search_rank=Case(
                When(name__istartswith=search, then=Value(0)),
                When(name__icontains=search, then=Value(1)),
                When(brand__name__icontains=search, then=Value(2)),
                default=Value(3),
            )
        )
    else:
        qs = qs.annotate(search_rank=Value(0))

    if params["min_price"] is not None:
        qs = qs.filter(price__gte=params["min_price"])
    if params["max_price"] is not None:
        qs = qs.filter(price__lte=params["max_price"])
    if params["min_rating"] is not None:
        qs = qs.filter(rating__gte=params["min_rating"])
    if params["min_discount"] is not None:
        qs = qs.filter(discount_ratio__gte=float(params["min_discount"]) / 100)
    if params["in_stock"]:
        qs = qs.filter(stock__gt=0)

    return qs.order_by(*ORDERINGS[params["ordering"]], "id")


def paginate(qs, params):
    total = qs.count()
    start = (params["page"] - 1) * params["page_size"]
    rows = list(qs[start : start + params["page_size"]])
    pages = max(1, (total + params["page_size"] - 1) // params["page_size"])
    return {
        "count": total,
        "page": params["page"],
        "page_size": params["page_size"],
        "pages": pages,
        "has_next": params["page"] < pages,
        "results": ProductListSerializer(rows, many=True).data,
    }


class BrandViewSet(viewsets.ModelViewSet):
    serializer_class = BrandSerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None
    lookup_field = "pk"

    def get_queryset(self):
        qs = Brand.objects.annotate(
            product_count=Count("products", filter=Q(products__is_active=True))
        )
        if not is_store_admin(self.request.user):
            qs = qs.filter(is_active=True)
        return qs

    def list(self, request, *args, **kwargs):
        params = {"all": is_store_admin(request.user)}
        data, hit = cache_aside(
            "catalog:brands",
            params,
            lambda: BrandSerializer(self.get_queryset(), many=True).data,
            TTL["brands"],
        )
        response = Response(data)
        response["X-Cache"] = "HIT" if hit else "MISS"
        return response


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None
    lookup_field = "pk"

    def get_queryset(self):
        qs = Category.objects.annotate(
            product_count=Count("products", filter=Q(products__is_active=True))
        )
        if not is_store_admin(self.request.user):
            qs = qs.filter(is_active=True)
        return qs.order_by("position", "name")

    def list(self, request, *args, **kwargs):
        params = {"all": is_store_admin(request.user)}
        data, hit = cache_aside(
            "catalog:categories",
            params,
            lambda: CategorySerializer(self.get_queryset(), many=True).data,
            TTL["categories"],
        )
        response = Response(data)
        response["X-Cache"] = "HIT" if hit else "MISS"
        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.products.exists():
            return Response(
                {
                    "message": (
                        f"'{instance.name}' still has {instance.products.count()} product(s). "
                        "Move or delete them first."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductViewSet(viewsets.ModelViewSet):
    """Browse with filters/sorting (cached) and full CRUD for managers."""

    lookup_value_regex = "[^/]+"

    def get_permissions(self):
        if self.action in {"list", "retrieve", "reviews", "related"}:
            return [AllowAny()]
        if self.action == "create_review":
            return [IsAuthenticated()]
        return [IsStoreAdmin()]

    def get_serializer_class(self):
        if self.action == "list":
            return ProductListSerializer
        if self.action == "retrieve":
            return ProductDetailSerializer
        if self.action in {"reviews", "create_review"}:
            return ReviewSerializer
        return ProductWriteSerializer

    # -- reads -------------------------------------------------------------
    def list(self, request, *args, **kwargs):
        params = normalise_params(request.query_params, admin=is_store_admin(request.user))
        data, hit = cache_aside(
            "catalog:products",
            params,
            lambda: paginate(build_product_queryset(params), params),
            TTL["product_list"],
        )
        response = Response(data)
        response["X-Cache"] = "HIT" if hit else "MISS"
        return response

    def _detail_payload(self, identifier):
        product = (
            Product.objects.select_related("brand", "category")
            .prefetch_related("images")
            .filter(Q(slug=identifier) | Q(pk=identifier) if str(identifier).isdigit() else Q(slug=identifier))
            .first()
        )
        if product is None:
            raise NotFound("Product not found.")
        related = (
            Product.objects.filter(category=product.category, is_active=True, stock__gt=0)
            .exclude(pk=product.pk)
            .order_by("-sold_count")[:8]
        )
        return {
            "product": ProductDetailSerializer(product).data,
            "related": ProductListSerializer(related, many=True).data,
        }

    def retrieve(self, request, *args, **kwargs):
        identifier = kwargs.get("pk")
        data, hit = cache_aside(
            "catalog:product",
            {"id": identifier},
            lambda: self._detail_payload(identifier),
            TTL["product_detail"],
        )
        product = Product.objects.filter(pk=data["product"]["id"]).first()
        if product:
            # Personal, uncached side effect: remember the visit.
            record_view(request.user, product)
        response = Response(data)
        response["X-Cache"] = "HIT" if hit else "MISS"
        return response

    @action(detail=True, methods=["get", "post"], url_path="reviews")
    def reviews(self, request, pk=None):
        product = get_object_or_404(Product, pk=pk)
        if request.method == "GET":
            rows = product.reviews.select_related("user")[:50]
            return Response(
                {
                    "count": product.rating_count,
                    "average": product.rating,
                    "results": ReviewSerializer(rows, many=True).data,
                }
            )
        return self.create_review(request, pk=product.pk)

    def create_review(self, request, pk=None):
        if not request.user.is_authenticated:
            raise NotAuthenticated("Sign in to write a review.")
        product = get_object_or_404(Product, pk=pk)
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if Review.objects.filter(product=product, user=request.user).exists():
            raise ValidationError({"detail": "You have already reviewed this product."})

        verified = Order.objects.filter(
            user=request.user,
            status=Order.Status.DELIVERED,
            items__product=product,
        ).exists()

        review = serializer.save(
            product=product, user=request.user, is_verified_purchase=verified
        )
        product.refresh_from_db()
        return Response(
            {"review": ReviewSerializer(review).data, "average": product.rating, "count": product.rating_count},
            status=status.HTTP_201_CREATED,
        )

    # -- writes ------------------------------------------------------------
    def create(self, request, *args, **kwargs):
        serializer = ProductWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        return Response(ProductWriteSerializer(product).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = ProductWriteSerializer(instance, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        return Response(ProductWriteSerializer(product).data)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def get_object(self):
        identifier = self.kwargs.get("pk")
        queryset = Product.objects.all()
        if str(identifier).isdigit():
            obj = queryset.filter(pk=identifier).first()
        else:
            obj = queryset.filter(slug=identifier).first()
        if obj is None:
            raise NotFound("Product not found.")
        self.check_object_permissions(self.request, obj)
        return obj

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.order_items.exists():
            return Response(
                {
                    "message": (
                        f"'{instance.name}' appears in past orders and cannot be deleted. "
                        "Mark it inactive instead."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        name = instance.name
        instance.delete()
        return Response({"message": f"'{name}' deleted."}, status=status.HTTP_200_OK)


class SearchSuggestView(APIView):
    """Autocomplete for the search bar (debounced on the client)."""

    permission_classes = [AllowAny]
    throttle_scope = "suggest"

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()[:40]
        if len(query) < 2:
            return Response({"query": query, "products": [], "categories": [], "brands": []})

        data, hit = cache_aside(
            "catalog:suggest",
            {"q": query.lower()},
            lambda: self._build(query),
            settings.CACHE_TTL["suggest"],
        )
        response = Response(data)
        response["X-Cache"] = "HIT" if hit else "MISS"
        return response

    def _build(self, query):
        products = (
            Product.objects.filter(is_active=True, name__icontains=query)
            .order_by("-sold_count")[:6]
        )
        categories = Category.objects.filter(name__icontains=query, is_active=True)[:3]
        brands = Brand.objects.filter(name__icontains=query, is_active=True)[:3]
        return {
            "query": query,
            "products": [
                {
                    "id": p.pk,
                    "name": p.name,
                    "slug": p.slug,
                    "price": str(p.price),
                    "image_url": p.image_url,
                }
                for p in products
            ],
            "categories": [{"id": c.pk, "name": c.name, "slug": c.slug} for c in categories],
            "brands": [{"id": b.pk, "name": b.name, "slug": b.slug} for b in brands],
        }


class HomeFeedView(APIView):
    """Everything the storefront needs for its landing rails."""

    permission_classes = [AllowAny]

    def get(self, request):
        data, hit = cache_aside("catalog:home", {}, self._build, settings.CACHE_TTL["home"])
        response = Response(data)
        response["X-Cache"] = "HIT" if hit else "MISS"
        return response

    def _build(self):
        base = Product.objects.filter(is_active=True).annotate(discount_ratio=DISCOUNT_RATIO)
        categories = Category.objects.annotate(
            product_count=Count("products", filter=Q(products__is_active=True))
        ).filter(is_active=True)[:10]
        brands = Brand.objects.filter(is_active=True)[:12]

        deals = base.filter(stock__gt=0, discount_ratio__gt=0.1).order_by("-discount_ratio")[:8]
        bestsellers = base.filter(stock__gt=0).order_by("-sold_count", "-rating")[:8]
        new_arrivals = base.filter(stock__gt=0).order_by("-created_at")[:8]
        top_rated = base.filter(stock__gt=0, rating_count__gt=0).order_by("-rating", "-rating_count")[:8]

        return {
            "categories": CategorySerializer(categories, many=True).data,
            "brands": BrandSerializer(brands, many=True).data,
            "rails": {
                "deals": ProductListSerializer(deals, many=True).data,
                "bestsellers": ProductListSerializer(bestsellers, many=True).data,
                "new_arrivals": ProductListSerializer(new_arrivals, many=True).data,
                "top_rated": ProductListSerializer(top_rated, many=True).data,
            },
            "stats": {
                "products": Product.objects.filter(is_active=True).count(),
                "categories": Category.objects.filter(is_active=True).count(),
                "brands": Brand.objects.filter(is_active=True).count(),
            },
        }


class PincodeCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, code):
        record = pincode_info(code)
        if not record:
            return Response(
                {
                    "pincode": code,
                    "serviceable": False,
                    "message": "We do not deliver to this pincode yet.",
                }
            )
        return Response(
            {
                "pincode": record.pincode,
                "serviceable": True,
                "city": record.city,
                "state": record.state,
                "cod_available": record.cod_available,
                "eta_min_days": record.eta_min_days,
                "eta_max_days": record.eta_max_days,
                "message": f"Delivering to {record.city} in {record.eta_min_days}-{record.eta_max_days} days",
            }
        )


class WishlistViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        rows = WishlistItem.objects.filter(user=request.user).select_related("product")
        products = [row.product for row in rows if row.product.is_active]
        return Response(
            {
                "count": len(products),
                "ids": [p.pk for p in products],
                "results": ProductListSerializer(products, many=True).data,
            }
        )

    def create(self, request):
        product = get_object_or_404(Product, pk=request.data.get("product"))
        item, created = WishlistItem.objects.get_or_create(user=request.user, product=product)
        if not created:
            item.delete()
        count = WishlistItem.objects.filter(user=request.user).count()
        return Response(
            {
                "wishlisted": created,
                "message": "Saved to your wishlist." if created else "Removed from your wishlist.",
                "count": count,
            }
        )

    @action(detail=True, methods=["delete"], url_path="remove")
    def remove(self, request, pk=None):
        WishlistItem.objects.filter(user=request.user, product_id=pk).delete()
        return Response({"wishlisted": False, "count": WishlistItem.objects.filter(user=request.user).count()})


class RecentlyViewedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = RecentlyViewed.objects.filter(user=request.user).select_related("product")[:12]
        products = [row.product for row in rows if row.product.is_active]
        return Response({"results": ProductListSerializer(products, many=True).data})


class LiveCouponsView(APIView):
    """Public marketing strip: today's bank offers and coupon codes."""

    permission_classes = [AllowAny]

    def get(self, request):
        data, hit = cache_aside(
            "catalog:coupons",
            {},
            lambda: [
                {
                    "code": coupon.code,
                    "description": coupon.description,
                    "discount_type": coupon.discount_type,
                    "value": str(coupon.value),
                    "min_order_value": str(coupon.min_order_value),
                    "max_discount": str(coupon.max_discount or ""),
                }
                for coupon in Coupon.objects.filter(is_active=True)[:8]
                if coupon.is_live
            ],
            TTL["categories"],
        )
        response = Response({"results": data})
        response["X-Cache"] = "HIT" if hit else "MISS"
        return response
