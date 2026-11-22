"""Admin console API: KPIs, coupon management, returns desk and customers."""

import datetime
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from ..cache import cache_aside
from ..models import (
    Coupon,
    Order,
    OrderItem,
    Product,
    ReturnRequest,
    Role,
    User,
    inr,
)
from ..permissions import IsStoreAdmin
from ..serializers import CouponSerializer, ReturnRequestSerializer
from ..services import resolve_return

MONEY = DecimalField(max_digits=12, decimal_places=2)


class DashboardView(APIView):
    """Everything the store manager needs at a glance."""

    permission_classes = [IsStoreAdmin]

    def get(self, request):
        data, hit = cache_aside(
            "admin:dashboard",
            {},
            self._build,
            15,  # short TTL: fulfilment numbers move during the day
        )
        response = Response(data)
        response["X-Cache"] = "HIT" if hit else "MISS"
        return response

    def _build(self):
        now = timezone.localtime()
        today = now.date()
        start = today - datetime.timedelta(days=13)

        paid_orders = Order.objects.exclude(status=Order.Status.CANCELLED)
        revenue = paid_orders.aggregate(total=Coalesce(Sum("total_amount"), Decimal("0.00"), output_field=MONEY))["total"]
        units = OrderItem.objects.filter(order__in=paid_orders).aggregate(
            total=Coalesce(Sum("quantity"), 0)
        )["total"]

        rows = (
            paid_orders.filter(created_at__date__gte=start)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(revenue=Coalesce(Sum("total_amount"), Decimal("0.00")), orders=Count("id"))
            .order_by("day")
        )
        by_day = {row["day"]: row for row in rows}
        series = []
        for offset in range(14):
            day = start + datetime.timedelta(days=offset)
            row = by_day.get(day)
            series.append(
                {
                    "date": day.isoformat(),
                    "label": day.strftime("%d %b"),
                    "revenue": float(row["revenue"]) if row else 0.0,
                    "orders": row["orders"] if row else 0,
                }
            )

        status_counts = {value: 0 for value, _ in Order.Status.choices}
        for row in Order.objects.values("status").annotate(count=Count("id")):
            status_counts[row["status"]] = row["count"]

        low_stock = Product.objects.filter(is_active=True, stock__lt=6).order_by("stock")[:10]

        top_products = (
            Product.objects.filter(is_active=True)
            .annotate(revenue=Coalesce(Sum(F("price") * F("sold_count")), Decimal("0.00")))
            .order_by("-sold_count")[:6]
        )

        recent = (
            Order.objects.select_related("user")
            .prefetch_related("items")
            .order_by("-created_at")[:8]
        )

        delivered = status_counts.get(Order.Status.DELIVERED, 0)
        placed = status_counts.get(Order.Status.PLACED, 0)
        packed = status_counts.get(Order.Status.PACKED, 0)
        shipped = status_counts.get(Order.Status.SHIPPED, 0)
        out_for_delivery = status_counts.get(Order.Status.OUT_FOR_DELIVERY, 0)
        cancelled = status_counts.get(Order.Status.CANCELLED, 0)
        total_orders = Order.objects.count()

        return {
            "kpis": {
                "revenue": revenue,
                "orders": total_orders,
                "units_sold": units,
                "customers": User.objects.filter(role=Role.CUSTOMER).count(),
                "average_order_value": (
                    inr(revenue / total_orders) if total_orders else Decimal("0.00")
                ),
                "delivered": delivered,
                "cancelled": cancelled,
                "pending_fulfilment": placed + packed + shipped + out_for_delivery,
                "low_stock": Product.objects.filter(is_active=True, stock__lt=6).count(),
                "returns_open": ReturnRequest.objects.exclude(
                    status__in=[ReturnRequest.Status.REJECTED, ReturnRequest.Status.REFUNDED]
                ).count(),
                "active_coupons": Coupon.objects.filter(is_active=True).count(),
                "cancellation_rate": round(cancelled / total_orders * 100, 1) if total_orders else 0.0,
            },
            "revenue_series": series,
            "status_counts": status_counts,
            "low_stock": [
                {
                    "id": product.pk,
                    "name": product.name,
                    "stock": product.stock,
                    "price": product.price,
                    "slug": product.slug,
                }
                for product in low_stock
            ],
            "top_products": [
                {
                    "id": product.pk,
                    "name": product.name,
                    "sold_count": product.sold_count,
                    "price": product.price,
                    "image_url": product.image_url,
                    "slug": product.slug,
                }
                for product in top_products
            ],
            "recent_orders": [
                {
                    "id": order.pk,
                    "order_number": order.order_number,
                    "customer": order.user.get_full_name() or order.user.username,
                    "status": order.status,
                    "total_amount": order.total_amount,
                    "item_count": sum(item.quantity for item in order.items.all()),
                    "created_at": order.created_at,
                    "payment_method": order.payment_method,
                }
                for order in recent
            ],
            "generated_at": timezone.now(),
        }


class CouponAdminViewSet(viewsets.ModelViewSet):
    queryset = Coupon.objects.all()
    serializer_class = CouponSerializer
    permission_classes = [IsStoreAdmin]

    def perform_destroy(self, instance):
        if instance.orders.exists():
            instance.is_active = False
            instance.save(update_fields=["is_active"])
            return
        instance.delete()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        retired = instance.orders.exists()
        self.perform_destroy(instance)
        return Response(
            {
                "message": (
                    f"{instance.code} was used by past orders, so it is now deactivated."
                    if retired
                    else f"{instance.code} deleted."
                )
            },
            status=status.HTTP_200_OK,
        )


class ReturnAdminViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ReturnRequestSerializer
    permission_classes = [IsStoreAdmin]
    pagination_class = None

    def get_queryset(self):
        queryset = ReturnRequest.objects.select_related("order", "user").order_by("-created_at")
        state = (self.request.query_params.get("status") or "").strip()
        if state and state.lower() != "all":
            queryset = queryset.filter(status=state)
        return queryset

    def list(self, request, *args, **kwargs):
        rows = list(self.get_queryset()[:100])
        counts = {}
        for value, _ in ReturnRequest.Status.choices:
            counts[value] = ReturnRequest.objects.filter(status=value).count()
        payload = []
        for row in rows:
            data = ReturnRequestSerializer(row).data
            data["customer"] = row.user.get_full_name() or row.user.username
            data["order_total"] = row.order.total_amount
            data["delivered_at"] = row.order.delivered_at
            payload.append(data)
        return Response({"count": len(payload), "status_counts": counts, "results": payload})

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request, pk=None):
        return_request = get_object_or_404(ReturnRequest, pk=pk)
        action_name = (request.data.get("action") or "").strip()
        if action_name not in {"approve", "reject", "refund"}:
            raise ValidationError({"action": "Choose approve, reject or refund."})
        return_request = resolve_return(
            return_request,
            action=action_name,
            admin_note=(request.data.get("admin_note") or "").strip(),
        )
        messages = {
            "approve": "Return approved - pickup scheduled.",
            "reject": "Return rejected and the order is back to Delivered.",
            "refund": "Refund processed and stock restored.",
        }
        return Response({"message": messages[action_name], "return": ReturnRequestSerializer(return_request).data})


class CustomerAdminView(APIView):
    permission_classes = [IsStoreAdmin]

    def get(self, request):
        customers = (
            User.objects.filter(role=Role.CUSTOMER)
            .annotate(
                order_count=Count("orders", distinct=True),
                spend=Coalesce(Sum("orders__total_amount"), Decimal("0.00"), output_field=MONEY),
            )
            .order_by("-spend", "username")[:100]
        )
        return Response(
            {
                "count": len(customers),
                "results": [
                    {
                        "id": user.pk,
                        "username": user.username,
                        "display_name": user.get_full_name() or user.username,
                        "email": user.email,
                        "phone": user.phone,
                        "date_joined": user.date_joined,
                        "order_count": user.order_count,
                        "spend": user.spend,
                    }
                    for user in customers
                ],
            }
        )


class AdminOverviewPulseView(APIView):
    """Fast polling endpoint for the console's live order feed."""

    permission_classes = [IsStoreAdmin]

    def get(self, request):
        latest = Order.objects.order_by("-updated_at").first()
        recent_events = (
            Order.objects.select_related("user").order_by("-created_at")[:5]
        )
        return Response(
            {
                "active": Order.objects.filter(
                    status__in=[
                        Order.Status.PLACED,
                        Order.Status.PACKED,
                        Order.Status.SHIPPED,
                        Order.Status.OUT_FOR_DELIVERY,
                    ]
                ).count(),
                "latest": (
                    {
                        "id": latest.pk,
                        "order_number": latest.order_number,
                        "status": latest.status,
                        "customer": latest.user.get_full_name() or latest.user.username,
                        "total_amount": latest.total_amount,
                        "updated_at": latest.updated_at,
                    }
                    if latest
                    else None
                ),
                "new_orders": [
                    {
                        "id": order.pk,
                        "order_number": order.order_number,
                        "status": order.status,
                        "customer": order.user.get_full_name() or order.user.username,
                        "created_at": order.created_at,
                    }
                    for order in recent_events
                ],
                "server_time": timezone.now(),
            }
        )
