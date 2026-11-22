"""Access control for the store API."""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Role


def is_store_admin(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (user.role == Role.ADMIN or user.is_superuser)
    )


class IsStoreAdmin(BasePermission):
    """Store managers only (Django superusers included)."""

    message = "Only store managers can perform this action."

    def has_permission(self, request, view):
        return is_store_admin(request.user)


class IsAdminOrReadOnly(BasePermission):
    """Anyone can read the catalog; only store managers can change it."""

    message = "Only store managers can perform this action."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return is_store_admin(request.user)


class IsOwnerOrAdmin(BasePermission):
    """Object is visible to its owner and to store managers."""

    message = "You do not have access to this resource."

    def has_object_permission(self, request, view, obj):
        owner = getattr(obj, "user", None)
        if owner == request.user:
            return True
        return is_store_admin(request.user)
