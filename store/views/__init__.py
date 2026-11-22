"""Public surface of the API view package."""

from .admin_console import (
    AdminOverviewPulseView,
    CouponAdminViewSet,
    CustomerAdminView,
    DashboardView,
    ReturnAdminViewSet,
)
from .auth import AddressViewSet, LoginView, LogoutView, MeView, RegisterView
from .cart import CartCouponView, CartItemView, CartQuoteView, CartView, CouponStripView
from .catalog import (
    BrandViewSet,
    CategoryViewSet,
    HomeFeedView,
    LiveCouponsView,
    PincodeCheckView,
    ProductViewSet,
    RecentlyViewedView,
    SearchSuggestView,
    WishlistViewSet,
)
from .orders import (
    OrderCancelView,
    OrderDetailView,
    OrderInvoiceView,
    OrderListCreateView,
    OrderReturnView,
    OrderStatusView,
    OrderStreamView,
    OrderSummaryView,
)
from .system import (
    CacheResetView,
    CacheStatsView,
    CacheWarmView,
    HealthView,
    SimulateRequestView,
)

__all__ = [
    "AddressViewSet",
    "AdminOverviewPulseView",
    "BrandViewSet",
    "CacheResetView",
    "CacheStatsView",
    "CacheWarmView",
    "CartCouponView",
    "CartItemView",
    "CartQuoteView",
    "CartView",
    "CategoryViewSet",
    "CouponAdminViewSet",
    "CouponStripView",
    "CustomerAdminView",
    "DashboardView",
    "HealthView",
    "HomeFeedView",
    "LiveCouponsView",
    "LoginView",
    "LogoutView",
    "MeView",
    "OrderCancelView",
    "OrderDetailView",
    "OrderInvoiceView",
    "OrderListCreateView",
    "OrderReturnView",
    "OrderStatusView",
    "OrderStreamView",
    "OrderSummaryView",
    "PincodeCheckView",
    "ProductViewSet",
    "RecentlyViewedView",
    "RegisterView",
    "ReturnAdminViewSet",
    "SearchSuggestView",
    "SimulateRequestView",
    "WishlistViewSet",
]
