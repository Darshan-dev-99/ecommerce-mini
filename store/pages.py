"""Server-rendered page shells.

Every shell is static HTML: all data arrives from the REST API through
fetch(), so no page ever needs a reload to show fresh data.
"""

from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie

from .permissions import is_store_admin


def _login_redirect(request):
    return redirect(f"{reverse('store:login')}?next={request.path}")


def _admin_only(request, template, nav, extra=None):
    """Common guard for console pages."""
    if not request.user.is_authenticated:
        return _login_redirect(request)
    if not is_store_admin(request.user):
        return redirect("store:home")
    context = {"nav": nav}
    context.update(extra or {})
    return render(request, template, context)


# --------------------------------------------------------------------------
# Storefront
# --------------------------------------------------------------------------


@ensure_csrf_cookie
def home(request):
    return render(request, "store/home.html", {"nav": "home"})


@ensure_csrf_cookie
def shop(request):
    return render(request, "store/shop.html", {"nav": "shop"})


@ensure_csrf_cookie
def product_detail(request, slug):
    return render(request, "store/product.html", {"nav": "shop", "slug": slug})


@ensure_csrf_cookie
def offers(request):
    return render(request, "store/offers.html", {"nav": "offers"})


@ensure_csrf_cookie
def architecture(request):
    return render(request, "store/architecture.html", {"nav": "architecture"})


@ensure_csrf_cookie
def login_page(request):
    return render(request, "store/login.html", {"nav": "login", "mode": "login"})


@ensure_csrf_cookie
def register_page(request):
    return render(request, "store/register.html", {"nav": "register", "mode": "register"})


# --------------------------------------------------------------------------
# Signed-in customer pages
# --------------------------------------------------------------------------


@ensure_csrf_cookie
def cart_page(request):
    if not request.user.is_authenticated:
        return _login_redirect(request)
    return render(request, "store/cart.html", {"nav": "cart"})


@ensure_csrf_cookie
def checkout_page(request):
    if not request.user.is_authenticated:
        return _login_redirect(request)
    return render(request, "store/checkout.html", {"nav": "cart"})


@ensure_csrf_cookie
def orders_page(request):
    if not request.user.is_authenticated:
        return _login_redirect(request)
    return render(request, "store/orders.html", {"nav": "orders"})


@ensure_csrf_cookie
def order_detail_page(request, pk):
    if not request.user.is_authenticated:
        return _login_redirect(request)
    return render(request, "store/order_detail.html", {"nav": "orders", "order_id": pk})


@ensure_csrf_cookie
def wishlist_page(request):
    if not request.user.is_authenticated:
        return _login_redirect(request)
    return render(request, "store/wishlist.html", {"nav": "wishlist"})


@ensure_csrf_cookie
def account_page(request):
    if not request.user.is_authenticated:
        return _login_redirect(request)
    return render(request, "store/account.html", {"nav": "account"})


# --------------------------------------------------------------------------
# Admin console
# --------------------------------------------------------------------------


@never_cache
@ensure_csrf_cookie
def dashboard_page(request):
    return _admin_only(request, "store/dashboard.html", "dashboard")


@never_cache
@ensure_csrf_cookie
def manage_products_page(request):
    return _admin_only(request, "store/manage_products.html", "manage_products")


@never_cache
@ensure_csrf_cookie
def manage_orders_page(request):
    return _admin_only(request, "store/manage_orders.html", "manage_orders")


@never_cache
@ensure_csrf_cookie
def manage_coupons_page(request):
    return _admin_only(request, "store/manage_coupons.html", "manage_coupons")


@never_cache
@ensure_csrf_cookie
def manage_returns_page(request):
    return _admin_only(request, "store/manage_returns.html", "manage_returns")
