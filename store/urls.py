"""URL routing for the storefront, the REST API and the admin console."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import pages, views

app_name = "store"

router = DefaultRouter()
router.register("brands", views.BrandViewSet, basename="brand")
router.register("categories", views.CategoryViewSet, basename="category")
router.register("products", views.ProductViewSet, basename="product")
router.register("wishlist", views.WishlistViewSet, basename="wishlist")
router.register("addresses", views.AddressViewSet, basename="address")

console = DefaultRouter()
console.register("coupons", views.CouponAdminViewSet, basename="admin-coupon")
console.register("returns", views.ReturnAdminViewSet, basename="admin-return")

api_patterns = [
    # ---------------------------------------------------------- accounts
    path("auth/register/", views.RegisterView.as_view(), name="api-register"),
    path("auth/login/", views.LoginView.as_view(), name="api-login"),
    path("auth/logout/", views.LogoutView.as_view(), name="api-logout"),
    path("auth/me/", views.MeView.as_view(), name="api-me"),
    # ----------------------------------------------------------- catalog
    path("home/", views.HomeFeedView.as_view(), name="api-home"),
    path("search/suggest/", views.SearchSuggestView.as_view(), name="api-suggest"),
    path("pincodes/<str:code>/", views.PincodeCheckView.as_view(), name="api-pincode"),
    path("offers/", views.LiveCouponsView.as_view(), name="api-offers"),
    path("recently-viewed/", views.RecentlyViewedView.as_view(), name="api-recent"),
    # -------------------------------------------------------------- cart
    path("cart/", views.CartView.as_view(), name="api-cart"),
    path("cart/items/", views.CartItemView.as_view(), name="api-cart-add"),
    path("cart/items/<int:pk>/", views.CartItemView.as_view(), name="api-cart-item"),
    path("cart/coupon/", views.CartCouponView.as_view(), name="api-cart-coupon"),
    path("cart/quote/", views.CartQuoteView.as_view(), name="api-cart-quote"),
    path("cart/offers/", views.CouponStripView.as_view(), name="api-cart-offers"),
    # ------------------------------------------------------------ orders
    path("orders/", views.OrderListCreateView.as_view(), name="api-orders"),
    path("orders/summary/", views.OrderSummaryView.as_view(), name="api-order-summary"),
    path("orders/<int:pk>/", views.OrderDetailView.as_view(), name="api-order"),
    path("orders/<int:pk>/cancel/", views.OrderCancelView.as_view(), name="api-order-cancel"),
    path("orders/<int:pk>/status/", views.OrderStatusView.as_view(), name="api-order-status"),
    path("orders/<int:pk>/return/", views.OrderReturnView.as_view(), name="api-order-return"),
    path("orders/<int:pk>/invoice/", views.OrderInvoiceView.as_view(), name="api-order-invoice"),
    path("orders/<int:pk>/stream/", views.OrderStreamView.as_view(), name="api-order-stream"),
    # ------------------------------------------------------------- admin
    path("admin/dashboard/", views.DashboardView.as_view(), name="api-dashboard"),
    path("admin/overview/", views.AdminOverviewPulseView.as_view(), name="api-admin-overview"),
    path("admin/customers/", views.CustomerAdminView.as_view(), name="api-customers"),
    path("admin/", include(console.urls)),
    # ------------------------------------------------------------ system
    path("system/cache-stats/", views.CacheStatsView.as_view(), name="api-cache-stats"),
    path("system/cache/warm/", views.CacheWarmView.as_view(), name="api-cache-warm"),
    path("system/cache/reset/", views.CacheResetView.as_view(), name="api-cache-reset"),
    path("system/simulate/", views.SimulateRequestView.as_view(), name="api-simulate"),
    path("system/health/", views.HealthView.as_view(), name="api-health"),
    path("", include(router.urls)),
]

urlpatterns = [
    # ------------------------------------------------------------ pages
    path("", pages.home, name="home"),
    path("shop/", pages.shop, name="shop"),
    path("p/<str:slug>/", pages.product_detail, name="product"),
    path("offers/", pages.offers, name="offers"),
    path("architecture/", pages.architecture, name="architecture"),
    path("login/", pages.login_page, name="login"),
    path("register/", pages.register_page, name="register"),
    path("cart/", pages.cart_page, name="cart"),
    path("checkout/", pages.checkout_page, name="checkout"),
    path("orders/", pages.orders_page, name="orders"),
    path("orders/<int:pk>/", pages.order_detail_page, name="order-detail"),
    path("wishlist/", pages.wishlist_page, name="wishlist"),
    path("account/", pages.account_page, name="account"),
    path("manage/", pages.dashboard_page, name="dashboard"),
    path("manage/products/", pages.manage_products_page, name="manage-products"),
    path("manage/orders/", pages.manage_orders_page, name="manage-orders"),
    path("manage/coupons/", pages.manage_coupons_page, name="manage-coupons"),
    path("manage/returns/", pages.manage_returns_page, name="manage-returns"),
    # -------------------------------------------------------------- api
    path("api/", include(api_patterns)),
]
