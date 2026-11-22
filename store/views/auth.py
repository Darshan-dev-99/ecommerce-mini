"""Authentication, profile and address book endpoints."""

from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.db.models import ProtectedError
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Address
from ..serializers import AddressSerializer, LoginSerializer, RegisterSerializer, UserSerializer


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        auth_login(request, user)
        return Response({"user": UserSerializer(user).data}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        auth_login(request, user)
        return Response({"user": UserSerializer(user).data})


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        auth_logout(request)
        return Response({"detail": "Logged out."})


class MeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"authenticated": False, "user": None})
        return Response(
            {
                "authenticated": True,
                "user": UserSerializer(request.user).data,
                "default_address": (
                    AddressSerializer(
                        request.user.addresses.filter(is_default=True).first()
                        or request.user.addresses.first()
                    ).data
                    if request.user.addresses.exists()
                    else None
                ),
            }
        )

    def patch(self, request):
        if not request.user.is_authenticated:
            raise ValidationError({"detail": "Authentication required."})
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"user": serializer.data})


class AddressViewSet(viewsets.ModelViewSet):
    """The signed-in user's address book - always scoped to the owner."""

    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError({"detail": "This address is used by an existing order."})
        return Response(status=status.HTTP_204_NO_CONTENT)
