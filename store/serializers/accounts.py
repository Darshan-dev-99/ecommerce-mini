"""Accounts serializers: users, registration and saved addresses."""

import re

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from ..models import Address, Cart, Role, User

PHONE_RE = re.compile(r"^[6-9]\d{9}$")
PINCODE_RE = re.compile(r"^[1-9]\d{5}$")


class UserSerializer(serializers.ModelSerializer):
    is_store_admin = serializers.BooleanField(read_only=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "phone",
            "is_store_admin",
            "display_name",
        ]
        read_only_fields = ["id", "username", "role"]

    def get_display_name(self, obj):
        return obj.get_full_name() or obj.username


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    phone = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ["username", "email", "password", "password_confirm", "phone", "first_name", "last_name"]

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("That username is already taken.")
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("That email is already registered.")
        return value

    def validate_phone(self, value):
        value = (value or "").strip()
        if value and not PHONE_RE.match(value):
            raise serializers.ValidationError("Enter a valid 10 digit Indian mobile number.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "The two passwords do not match."}
            )
        validate_password(attrs["password"])
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        user = User(**validated_data, role=Role.CUSTOMER)
        user.set_password(password)
        user.save()
        Cart.objects.get_or_create(user=user)
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["username"].strip(),
            password=attrs["password"],
        )
        if not user:
            raise serializers.ValidationError({"detail": "Invalid username or password."})
        if not user.is_active:
            raise serializers.ValidationError({"detail": "This account is disabled."})
        attrs["user"] = user
        return attrs


class AddressSerializer(serializers.ModelSerializer):
    formatted = serializers.CharField(read_only=True)

    class Meta:
        model = Address
        fields = [
            "id",
            "label",
            "full_name",
            "phone",
            "line1",
            "line2",
            "city",
            "state",
            "pincode",
            "is_default",
            "formatted",
        ]

    def validate_phone(self, value):
        value = (value or "").strip()
        if not PHONE_RE.match(value):
            raise serializers.ValidationError("Enter a valid 10 digit Indian mobile number.")
        return value

    def validate_pincode(self, value):
        value = (value or "").strip()
        if not PINCODE_RE.match(value):
            raise serializers.ValidationError("Enter a valid 6 digit pincode.")
        return value

    def validate_full_name(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("Enter the recipient's full name.")
        return value

    def create(self, validated_data):
        user = validated_data.pop("user")
        if not user.addresses.exists():
            validated_data["is_default"] = True
        return Address.objects.create(user=user, **validated_data)
