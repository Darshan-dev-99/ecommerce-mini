"""Orders: placement, history, tracking timeline, cancellation and returns."""

import json
import time

from django.conf import settings
from django.db import close_old_connections
from django.http import HttpResponseForbidden, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Order, ReturnRequest
from ..permissions import is_store_admin
from ..serializers import (
    OrderSerializer,
    PlaceOrderSerializer,
    ReturnRequestCreateSerializer,
    ReturnRequestSerializer,
)
from ..services import cancel_order, checkout, request_return, update_order_status


def visible_order(request, pk) -> Order:
    """Fetch an order the caller is allowed to see, or fail loudly."""
    queryset = Order.objects.select_related("user", "coupon").prefetch_related(
        "items", "events", "returns"
    )
    order = get_object_or_404(queryset, pk=pk)
    if order.user_id != request.user.pk and not is_store_admin(request.user):
        raise PermissionDenied("This order belongs to another customer.")
    return order


class OrderListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = (
            Order.objects.select_related("user")
            .prefetch_related("items", "events", "returns")
            .order_by("-created_at")
        )
        if not is_store_admin(request.user):
            queryset = queryset.filter(user=request.user)

        status_filter = (request.query_params.get("status") or "").strip()
        if status_filter and status_filter.lower() != "all":
            queryset = queryset.filter(status=status_filter)

        search = (request.query_params.get("q") or "").strip()
        if search:
            queryset = queryset.filter(order_number__icontains=search) | queryset.filter(
                shipping_name__icontains=search
            )

        rows = list(queryset[:80])
        counts = {}
        base = Order.objects.all() if is_store_admin(request.user) else Order.objects.filter(user=request.user)
        for value, _ in Order.Status.choices:
            counts[value] = base.filter(status=value).count()

        return Response(
            {
                "count": len(rows),
                "results": OrderSerializer(rows, many=True).data,
                "status_counts": counts,
                "is_admin": is_store_admin(request.user),
            }
        )

    def post(self, request):
        serializer = PlaceOrderSerializer(
            data=request.data, context={"user": request.user, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        order = checkout(
            request.user,
            address=serializer.validated_data["address"],
            payment_method=serializer.validated_data["payment_method"],
            coupon_code=serializer.validated_data.get("coupon_code", ""),
        )
        return Response(
            {
                "message": f"Order {order.order_number} placed successfully.",
                "order": OrderSerializer(order).data,
            },
            status=status.HTTP_201_CREATED,
        )


class OrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return Response(OrderSerializer(visible_order(request, pk)).data)


class OrderCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        order = visible_order(request, pk)
        reason = (request.data.get("reason") or "").strip()
        by_admin = is_store_admin(request.user) and order.user_id != request.user.pk
        order = cancel_order(
            order,
            by_admin=by_admin,
            reason=reason or ("Cancelled by store" if by_admin else "Cancelled by customer"),
        )
        return Response(
            {
                "message": (
                    f"Order {order.order_number} cancelled. "
                    + (
                        "Refund initiated to your original payment method."
                        if order.payment_status == Order.PaymentStatus.REFUNDED
                        else "Stock has been restored."
                    )
                ),
                "order": OrderSerializer(order).data,
            }
        )


class OrderStatusView(APIView):
    """Store managers advance the fulfilment pipeline."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if not is_store_admin(request.user):
            raise PermissionDenied("Only store managers can update order status.")
        order = get_object_or_404(Order, pk=pk)
        new_status = (request.data.get("status") or "").strip()
        if new_status not in dict(Order.Status.choices):
            raise ValidationError({"status": f"'{new_status}' is not a valid order status."})
        order = update_order_status(
            order,
            new_status,
            note=(request.data.get("note") or "").strip(),
            location=(request.data.get("location") or "").strip(),
        )
        return Response(
            {"message": f"Order {order.order_number} marked '{order.status}'.", "order": OrderSerializer(order).data}
        )


class OrderReturnView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        order = visible_order(request, pk)
        if order.user_id != request.user.pk:
            raise PermissionDenied("Only the customer can request a return.")
        serializer = ReturnRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_obj = request_return(
            order,
            request.user,
            reason=serializer.validated_data["reason"],
            comment=serializer.validated_data.get("comment", ""),
        )
        return Response(
            {
                "message": "Return requested. We will arrange a pickup within 48 hours.",
                "return": ReturnRequestSerializer(request_obj).data,
                "order": OrderSerializer(visible_order(request, pk)).data,
            },
            status=status.HTTP_201_CREATED,
        )


class OrderInvoiceView(View):
    """Printable GST invoice (opens in a new tab).

    A plain Django view on purpose: the response is HTML, not JSON, so it must
    not go through DRF's content negotiation.
    """

    def get(self, request, pk):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('store:login')}?next={request.path}")
        order = get_object_or_404(
            Order.objects.select_related("user").prefetch_related("items"), pk=pk
        )
        if order.user_id != request.user.pk and not is_store_admin(request.user):
            return HttpResponseForbidden("This invoice belongs to another customer.")
        return render(
            request,
            "store/invoice.html",
            {"order": order, "items": order.items.all(), "store": settings.STORE},
        )


class OrderStreamView(APIView):
    """Server-Sent Events: live status updates while the customer watches.

    The browser opens one long-lived connection; the server polls the order
    row every few seconds and pushes a frame only when something changed.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        order = visible_order(request, pk)
        final = {
            Order.Status.CANCELLED,
            Order.Status.DELIVERED,
            Order.Status.RETURNED,
        }

        def frames():
            last = None
            started = time.monotonic()
            yield "retry: 4000\n\n"
            while time.monotonic() - started < 180:
                close_old_connections()
                current = (
                    Order.objects.select_related("user")
                    .prefetch_related("events")
                    .filter(pk=order.pk)
                    .first()
                )
                if current is None:
                    break
                payload = {
                    "id": current.pk,
                    "order_number": current.order_number,
                    "status": current.status,
                    "payment_status": current.payment_status,
                    "delivered_at": current.delivered_at.isoformat() if current.delivered_at else None,
                    "events": [
                        {
                            "status": event.status,
                            "note": event.note,
                            "location": event.location,
                            "created_at": event.created_at.isoformat(),
                        }
                        for event in current.events.all()
                    ],
                }
                if payload != last:
                    last = payload
                    yield f"event: order\ndata: {json.dumps(payload)}\n\n"
                if current.status in final:
                    break
                time.sleep(3)
                yield ": keep-alive\n\n"

        response = StreamingHttpResponse(frames(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class OrderSummaryView(APIView):
    """Tiny payload the storefront polls for the "my orders" badge."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Order.objects.filter(user=request.user)
        active = queryset.exclude(
            status__in=[Order.Status.CANCELLED, Order.Status.RETURNED]
        )
        latest = active.order_by("-updated_at").first()
        return Response(
            {
                "active": active.count(),
                "total": queryset.count(),
                "latest": (
                    {
                        "id": latest.pk,
                        "order_number": latest.order_number,
                        "status": latest.status,
                        "updated_at": latest.updated_at,
                        "delivery_eta": latest.delivery_eta,
                    }
                    if latest
                    else None
                ),
                "server_time": timezone.now(),
            }
        )
