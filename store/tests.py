"""Test suite for BazaarNoon - an India-first marketplace on Django + DRF.

Covers money maths (GST, delivery, COD, coupons), the cache-aside catalog,
cart mutations, atomic checkout, the order lifecycle, returns/refunds, the
seller console, cache telemetry and the server-rendered page shells.

Run with:  python manage.py test store -v 2
"""

import datetime
from decimal import Decimal

from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    Address,
    Brand,
    Cart,
    Category,
    Coupon,
    Order,
    Pincode,
    Product,
    ReturnRequest,
    Role,
    User,
)
from .services import (
    CheckoutError,
    delivery_fee_for,
    gst_component,
    quote,
    update_order_status,
    validate_coupon,
)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StoreTestBase(APITestCase):
    """Shared catalogue + accounts. Every test starts with a cold cache."""

    def setUp(self):
        cache.clear()

        self.brand = Brand.objects.create(name="Noise", tagline="Make some noise")
        self.category = Category.objects.create(name="Audio", icon="🎧")
        self.home_category = Category.objects.create(name="Home & Kitchen", icon="🏠")

        self.product = Product.objects.create(
            name="Noise Cancelling Headphones",
            brand=self.brand,
            category=self.category,
            description="Over-ear ANC headphones with 40 hour battery",
            mrp=Decimal("2999.00"),
            price=Decimal("1999.00"),
            stock=10,
            sold_count=88,
            rating=Decimal("4.3"),
            rating_count=152,
            delivery_days=2,
            warranty="1 year warranty",
            highlights=["Active noise cancellation", "40h playback"],
        )
        self.second = Product.objects.create(
            name="USB-C Cable",
            category=self.category,
            description="Braided 65W fast charging cable",
            mrp=Decimal("499.00"),
            price=Decimal("299.00"),
            stock=5,
            delivery_days=3,
        )
        self.out_of_stock = Product.objects.create(
            name="Sold Out Speaker",
            category=self.home_category,
            mrp=Decimal("999.00"),
            price=Decimal("799.00"),
            stock=0,
        )
        self.hidden = Product.objects.create(
            name="Hidden Gem",
            category=self.category,
            mrp=Decimal("399.00"),
            price=Decimal("199.00"),
            stock=7,
            is_active=False,
        )

        self.customer = User.objects.create_user(
            username="asha", password="Str0ngPass!23", role=Role.CUSTOMER,
            first_name="Asha", last_name="Rao", phone="9876543210",
        )
        self.other_customer = User.objects.create_user(
            username="robin", password="Str0ngPass!23", role=Role.CUSTOMER
        )
        self.admin = User.objects.create_user(
            username="avery", password="Str0ngPass!23", role=Role.ADMIN
        )

    # -- helpers -----------------------------------------------------------
    def login(self, user):
        self.client.force_authenticate(user=user)

    def make_address(self, user=None, pincode="560001", **overrides):
        payload = {
            "user": user or self.customer,
            "label": "Home",
            "full_name": "Asha Rao",
            "phone": "9876543210",
            "line1": "12 MG Road",
            "line2": "Indiranagar",
            "city": "Bengaluru",
            "state": "Karnataka",
            "pincode": pincode,
            "is_default": True,
        }
        payload.update(overrides)
        return Address.objects.create(**payload)

    def add_to_cart(self, product=None, quantity=1):
        product = product or self.product
        return self.client.post(
            reverse("store:api-cart-add"),
            {"product": product.pk, "quantity": quantity},
            format="json",
        )

    def cart_item(self, product=None, user=None):
        product = product or self.product
        return Cart.objects.get(user=user or self.customer).items.get(product=product)

    def place_order(self, user=None, product=None, quantity=1, payment_method="COD", coupon_code=""):
        user = user or self.customer
        product = product or self.product
        self.login(user)
        added = self.add_to_cart(product, quantity)
        self.assertIn(added.status_code, (200, 201), added.data)
        address = self.make_address(user)
        payload = {"address_id": address.pk, "payment_method": payment_method}
        if coupon_code:
            payload["coupon_code"] = coupon_code
        response = self.client.post(reverse("store:api-orders"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return Order.objects.get(pk=response.data["order"]["id"])

    def deliver(self, order):
        for step in (
            Order.Status.PACKED,
            Order.Status.SHIPPED,
            Order.Status.OUT_FOR_DELIVERY,
            Order.Status.DELIVERED,
        ):
            order = update_order_status(order, step)
        return order

    def make_delivered_order(self, user=None, product=None, quantity=1, payment_method="UPI"):
        order = self.place_order(
            user=user, product=product, quantity=quantity, payment_method=payment_method
        )
        return self.deliver(order)


# --------------------------------------------------------------------------
# Money
# --------------------------------------------------------------------------


class PricingTests(StoreTestBase):
    def test_gst_component_is_contained_in_an_inclusive_price(self):
        self.assertEqual(gst_component(Decimal("1180.00")), Decimal("180.00"))
        self.assertEqual(gst_component(Decimal("0")), Decimal("0.00"))

    def test_delivery_fees_respect_threshold_and_free_delivery_products(self):
        self.assertEqual(delivery_fee_for(Decimal("0")), Decimal("0.00"))
        self.assertEqual(delivery_fee_for(Decimal("498.00")), Decimal("49.00"))
        self.assertEqual(delivery_fee_for(Decimal("499.00")), Decimal("0.00"))
        self.product.free_delivery = True
        self.assertEqual(delivery_fee_for(Decimal("100.00"), [self.product]), Decimal("0.00"))

    def test_quote_combines_coupon_cod_fee_and_delivery(self):
        coupon = Coupon.objects.create(
            code="TEN",
            discount_type=Coupon.DiscountType.PERCENT,
            value=Decimal("10"),
            min_order_value=Decimal("0"),
            max_discount=Decimal("200"),
        )
        totals = quote(
            Decimal("2000.00"), coupon=coupon, payment_method=Order.PaymentMethod.COD
        )
        self.assertEqual(totals["discount_amount"], Decimal("200.00"))
        self.assertEqual(totals["delivery_fee"], Decimal("0.00"))
        self.assertEqual(totals["cod_fee"], Decimal("49.00"))
        self.assertEqual(totals["total_amount"], Decimal("1849.00"))
        self.assertEqual(totals["gst_amount"], gst_component(totals["total_amount"]))
        self.assertEqual(totals["free_delivery_gap"], Decimal("0.00"))

    def test_quote_reports_the_gap_to_free_delivery(self):
        totals = quote(Decimal("299.00"), payment_method=Order.PaymentMethod.UPI)
        self.assertEqual(totals["delivery_fee"], Decimal("49.00"))
        self.assertEqual(totals["cod_fee"], Decimal("0.00"))
        self.assertEqual(totals["free_delivery_gap"], Decimal("200.00"))

    def test_coupon_discount_respects_minimum_order_and_cap(self):
        coupon = Coupon.objects.create(
            code="BIG",
            discount_type=Coupon.DiscountType.PERCENT,
            value=Decimal("50"),
            min_order_value=Decimal("999"),
            max_discount=Decimal("300"),
        )
        self.assertEqual(coupon.discount_for(Decimal("500")), Decimal("0.00"))
        self.assertEqual(coupon.discount_for(Decimal("2000")), Decimal("300.00"))

        flat = Coupon.objects.create(
            code="FLAT100",
            discount_type=Coupon.DiscountType.FLAT,
            value=Decimal("100"),
            min_order_value=Decimal("0"),
        )
        self.assertEqual(flat.discount_for(Decimal("150")), Decimal("100.00"))
        self.assertEqual(flat.discount_for(Decimal("50")), Decimal("50.00"))

    def test_coupon_codes_are_uppercased_and_expiry_is_enforced(self):
        coupon = Coupon.objects.create(
            code=" new10 ",
            discount_type=Coupon.DiscountType.PERCENT,
            value=Decimal("10"),
            valid_to=timezone.now() - datetime.timedelta(days=1),
        )
        self.assertEqual(coupon.code, "NEW10")
        self.assertFalse(coupon.is_live)
        with self.assertRaises(CheckoutError):
            validate_coupon("NEW10", self.customer, Decimal("1000"))


# --------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------


class AuthTests(StoreTestBase):
    def test_register_creates_a_customer_with_a_cart_and_signs_them_in(self):
        response = self.client.post(
            reverse("store:api-register"),
            {
                "username": "newbie",
                "email": "new@example.com",
                "first_name": "New",
                "last_name": "Bie",
                "phone": "9812345678",
                "password": "Str0ngPass!23",
                "password_confirm": "Str0ngPass!23",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        user = User.objects.get(username="newbie")
        self.assertEqual(user.role, Role.CUSTOMER)
        self.assertTrue(user.check_password("Str0ngPass!23"))
        self.assertTrue(Cart.objects.filter(user=user).exists())

        me = self.client.get(reverse("store:api-me"))
        self.assertTrue(me.data["authenticated"])
        self.assertEqual(me.data["user"]["username"], "newbie")

    def test_register_rejects_mismatched_passwords_and_duplicate_usernames(self):
        bad = self.client.post(
            reverse("store:api-register"),
            {
                "username": "newbie",
                "email": "new@example.com",
                "password": "Str0ngPass!23",
                "password_confirm": "Different!23",
            },
            format="json",
        )
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)

        dupe = self.client.post(
            reverse("store:api-register"),
            {
                "username": "asha",
                "email": "asha@example.com",
                "password": "Str0ngPass!23",
                "password_confirm": "Str0ngPass!23",
            },
            format="json",
        )
        self.assertEqual(dupe.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_logout_cycle(self):
        response = self.client.post(
            reverse("store:api-login"),
            {"username": "asha", "password": "Str0ngPass!23"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["user"]["username"], "asha")

        me = self.client.get(reverse("store:api-me"))
        self.assertTrue(me.data["authenticated"])

        self.client.post(reverse("store:api-logout"), {}, format="json")
        me = self.client.get(reverse("store:api-me"))
        self.assertFalse(me.data["authenticated"])
        self.assertIsNone(me.data["user"])

    def test_login_rejects_wrong_password(self):
        response = self.client.post(
            reverse("store:api-login"),
            {"username": "asha", "password": "wrong-password"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_me_exposes_the_default_address(self):
        self.make_address()
        self.login(self.customer)
        data = self.client.get(reverse("store:api-me")).data
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["default_address"]["pincode"], "560001")

    def test_profile_can_be_updated(self):
        self.login(self.customer)
        response = self.client.patch(
            reverse("store:api-me"),
            {"first_name": "Asha", "phone": "9812345678"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.phone, "9812345678")

    def test_address_book_validates_indian_phone_and_pincode(self):
        self.login(self.customer)
        url = reverse("store:address-list")
        good = self.client.post(
            url,
            {
                "label": "Work",
                "full_name": "Asha Rao",
                "phone": "9876543210",
                "line1": "Embassy Tech Village",
                "city": "Bengaluru",
                "state": "Karnataka",
                "pincode": "560103",
                "is_default": True,
            },
            format="json",
        )
        self.assertEqual(good.status_code, status.HTTP_201_CREATED, good.data)

        bad = self.client.post(
            url,
            {
                "label": "Home",
                "full_name": "Asha Rao",
                "phone": "12345",
                "line1": "Somewhere",
                "city": "Bengaluru",
                "state": "Karnataka",
                "pincode": "12",
            },
            format="json",
        )
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", bad.data)
        self.assertIn("pincode", bad.data)

    def test_only_the_owner_sees_their_addresses(self):
        self.make_address(self.other_customer, line1="Someone else's flat")
        self.login(self.customer)
        data = self.client.get(reverse("store:address-list")).data
        self.assertEqual(data, [])


# --------------------------------------------------------------------------
# Catalog + cache-aside
# --------------------------------------------------------------------------


class CatalogApiTests(StoreTestBase):
    def test_list_hides_inactive_products_and_reports_cache_miss_then_hit(self):
        url = reverse("store:product-list")
        first = self.client.get(url)
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first["X-Cache"], "MISS")
        self.assertEqual(first.data["count"], 3)
        self.assertNotIn(self.hidden.pk, [row["id"] for row in first.data["results"]])

        second = self.client.get(url)
        self.assertEqual(second["X-Cache"], "HIT")
        self.assertEqual(second.data["count"], first.data["count"])

    def test_filters_and_ordering(self):
        url = reverse("store:product-list")

        search = self.client.get(url, {"search": "head"})
        self.assertEqual(search.data["count"], 1)
        self.assertEqual(search.data["results"][0]["id"], self.product.pk)

        cheapest = self.client.get(url, {"ordering": "price"})
        self.assertEqual(cheapest.data["results"][0]["id"], self.second.pk)

        in_stock = self.client.get(url, {"in_stock": "1"})
        self.assertEqual(in_stock.data["count"], 2)

        discounted = self.client.get(url, {"min_discount": "40"})
        self.assertEqual(discounted.data["count"], 1)
        self.assertEqual(discounted.data["results"][0]["id"], self.second.pk)

        priced = self.client.get(url, {"min_price": "1000"})
        self.assertEqual(priced.data["count"], 1)
        self.assertEqual(priced.data["results"][0]["id"], self.product.pk)

        by_category = self.client.get(url, {"category": self.home_category.slug})
        self.assertEqual(by_category.data["count"], 1)
        self.assertEqual(by_category.data["results"][0]["id"], self.out_of_stock.pk)

    def test_admins_can_list_inactive_products(self):
        self.login(self.admin)
        data = self.client.get(
            reverse("store:product-list"), {"include_inactive": "1"}
        ).data
        self.assertIn(self.hidden.pk, [row["id"] for row in data["results"]])

    def test_detail_by_slug_and_by_id_returns_related_products(self):
        by_slug = self.client.get(reverse("store:product-detail", args=[self.product.slug]))
        self.assertEqual(by_slug.status_code, status.HTTP_200_OK)
        self.assertEqual(by_slug.data["product"]["id"], self.product.pk)
        related_ids = [row["id"] for row in by_slug.data["related"]]
        self.assertNotIn(self.product.pk, related_ids)
        self.assertIn(self.second.pk, related_ids)

        by_id = self.client.get(reverse("store:product-detail", args=[self.product.pk]))
        self.assertEqual(by_id.status_code, status.HTTP_200_OK)

        missing = self.client.get(reverse("store:product-detail", args=["does-not-exist"]))
        self.assertEqual(missing.status_code, status.HTTP_404_NOT_FOUND)

    def test_search_suggest_ignores_very_short_queries(self):
        url = reverse("store:api-suggest")
        empty = self.client.get(url, {"q": "n"})
        self.assertEqual(empty.data["products"], [])

        data = self.client.get(url, {"q": "noi"}).data
        self.assertEqual(data["products"][0]["id"], self.product.pk)
        self.assertIn("Noise", [brand["name"] for brand in data["brands"]])

    def test_home_feed_exposes_rails_and_stats(self):
        data = self.client.get(reverse("store:api-home")).data
        self.assertEqual(data["stats"]["products"], 3)
        self.assertIn("deals", data["rails"])
        self.assertTrue(all(row["stock"] > 0 for row in data["rails"]["bestsellers"]))
        self.assertEqual(data["categories"][0]["name"], "Audio")

    def test_pincode_lookup(self):
        Pincode.objects.create(
            pincode="560001", city="Bengaluru", state="Karnataka",
            eta_min_days=2, eta_max_days=4, cod_available=True,
        )
        serviceable = self.client.get(reverse("store:api-pincode", args=["560001"]))
        self.assertTrue(serviceable.data["serviceable"])
        self.assertEqual(serviceable.data["city"], "Bengaluru")

        unknown = self.client.get(reverse("store:api-pincode", args=["999999"]))
        self.assertFalse(unknown.data["serviceable"])

    def test_public_offers_strip_lists_live_coupons(self):
        Coupon.objects.create(
            code="LIVE50", discount_type=Coupon.DiscountType.FLAT, value=Decimal("50")
        )
        Coupon.objects.create(
            code="DEAD50", discount_type=Coupon.DiscountType.FLAT,
            value=Decimal("50"), is_active=False,
        )
        codes = [row["code"] for row in self.client.get(reverse("store:api-offers")).data["results"]]
        self.assertIn("LIVE50", codes)
        self.assertNotIn("DEAD50", codes)

    def test_only_managers_can_write_the_catalog(self):
        payload = {
            "name": "boAt Rockerz 450",
            "category": self.category.pk,
            "brand": self.brand.pk,
            "price": "1499.00",
            "stock": 20,
        }
        url = reverse("store:product-list")

        self.login(self.customer)
        self.assertEqual(
            self.client.post(url, payload, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.login(self.admin)
        created = self.client.post(url, payload, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertEqual(created.data["mrp"], "1499.00")
        self.assertTrue(created.data["slug"])

        detail = reverse("store:product-detail", args=[created.data["id"]])
        updated = self.client.patch(detail, {"price": "1399.00"}, format="json")
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.data["price"], "1399.00")

        deleted = self.client.delete(detail)
        self.assertEqual(deleted.status_code, status.HTTP_200_OK)

    def test_product_in_past_orders_cannot_be_deleted(self):
        order = self.place_order()
        self.assertIsNotNone(order.pk)
        self.login(self.admin)
        response = self.client.delete(
            reverse("store:product-detail", args=[self.product.pk])
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cannot be deleted", response.data["message"])

    def test_category_with_products_cannot_be_deleted(self):
        self.login(self.admin)
        response = self.client.delete(
            reverse("store:category-detail", args=[self.category.pk])
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("product", response.data["message"].lower())


# --------------------------------------------------------------------------
# Cart
# --------------------------------------------------------------------------


class CartApiTests(StoreTestBase):
    def test_cart_requires_authentication(self):
        self.login(None)
        self.assertIn(
            self.client.get(reverse("store:api-cart")).status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_adding_a_product_returns_the_full_cart(self):
        self.login(self.customer)
        response = self.add_to_cart(quantity=2)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        cart = response.data["cart"]
        self.assertEqual(cart["item_count"], 2)
        self.assertEqual(cart["items"][0]["quantity"], 2)
        self.assertEqual(cart["subtotal"], "3998.00")
        self.assertEqual(cart["summary"]["delivery_fee"], Decimal("0.00"))

        again = self.add_to_cart(quantity=1)
        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertEqual(again.data["cart"]["items"][0]["quantity"], 3)
        self.assertEqual(len(again.data["cart"]["items"]), 1)

    def test_quantity_is_capped_by_stock(self):
        self.login(self.customer)
        too_many = self.add_to_cart(quantity=11)
        self.assertEqual(too_many.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Only 10", too_many.data["detail"])

        self.add_to_cart(quantity=1)
        item = self.cart_item()
        response = self.client.patch(
            reverse("store:api-cart-item", args=[item.pk]),
            {"quantity": 50},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        zero = self.client.patch(
            reverse("store:api-cart-item", args=[item.pk]),
            {"quantity": 0},
            format="json",
        )
        self.assertEqual(zero.status_code, status.HTTP_400_BAD_REQUEST)

    def test_out_of_stock_and_inactive_products_are_rejected(self):
        self.login(self.customer)
        self.assertEqual(self.add_to_cart(self.out_of_stock).status_code, 400)
        self.assertEqual(self.add_to_cart(self.hidden).status_code, 400)

    def test_quantity_patch_updates_the_live_summary(self):
        self.login(self.customer)
        self.add_to_cart(self.second, quantity=1)
        item = self.cart_item(self.second)
        response = self.client.patch(
            reverse("store:api-cart-item", args=[item.pk]),
            {"quantity": 3},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cart = response.data["cart"]
        self.assertEqual(cart["subtotal"], "897.00")
        self.assertEqual(cart["summary"]["delivery_fee"], Decimal("0.00"))

    def test_save_for_later_moves_the_line_out_of_the_cart(self):
        self.login(self.customer)
        self.add_to_cart(quantity=2)
        item = self.cart_item()
        response = self.client.patch(
            reverse("store:api-cart-item", args=[item.pk]),
            {"saved_for_later": True},
            format="json",
        )
        cart = response.data["cart"]
        self.assertEqual(cart["items"], [])
        self.assertEqual(len(cart["saved_items"]), 1)
        self.assertEqual(cart["item_count"], 0)
        self.assertEqual(cart["subtotal"], "0.00")

        # A cart with only saved-for-later lines cannot be checked out.
        self.make_address()
        response = self.client.post(
            reverse("store:api-orders"),
            {"address_id": Address.objects.first().pk, "payment_method": "COD"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_remove_item_and_clear_cart(self):
        self.login(self.customer)
        self.add_to_cart(self.product)
        self.add_to_cart(self.second)
        item = self.cart_item(self.product)
        removed = self.client.delete(reverse("store:api-cart-item", args=[item.pk]))
        self.assertEqual(removed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(removed.data["cart"]["items"]), 1)

        cleared = self.client.delete(reverse("store:api-cart"))
        self.assertEqual(cleared.data["items"], [])

    def test_coupons_can_be_applied_and_removed(self):
        Coupon.objects.create(
            code="SAVE10",
            discount_type=Coupon.DiscountType.PERCENT,
            value=Decimal("10"),
            min_order_value=Decimal("499"),
            max_discount=Decimal("200"),
        )
        self.login(self.customer)
        self.add_to_cart(self.product)

        applied = self.client.post(
            reverse("store:api-cart-coupon"), {"code": "save10"}, format="json"
        )
        self.assertEqual(applied.status_code, status.HTTP_200_OK, applied.data)
        self.assertEqual(applied.data["cart"]["coupon"]["code"], "SAVE10")
        self.assertEqual(applied.data["cart"]["summary"]["discount_amount"], Decimal("199.90"))

        unknown = self.client.post(
            reverse("store:api-cart-coupon"), {"code": "NOPE"}, format="json"
        )
        self.assertEqual(unknown.status_code, status.HTTP_400_BAD_REQUEST)

        removed = self.client.delete(reverse("store:api-cart-coupon"))
        self.assertIsNone(removed.data["cart"]["coupon"])

    def test_coupon_needs_the_minimum_order_value(self):
        Coupon.objects.create(
            code="BIGSPEND",
            discount_type=Coupon.DiscountType.FLAT,
            value=Decimal("500"),
            min_order_value=Decimal("5000"),
        )
        self.login(self.customer)
        self.add_to_cart(self.product)
        response = self.client.post(
            reverse("store:api-cart-coupon"), {"code": "BIGSPEND"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("more to use", response.data["detail"])

    def test_quote_switches_between_cod_and_prepaid(self):
        self.login(self.customer)
        self.add_to_cart(self.second)
        url = reverse("store:api-cart-quote")

        cod = self.client.post(url, {"payment_method": "COD"}, format="json").data
        self.assertEqual(cod["delivery_fee"], Decimal("49.00"))
        self.assertEqual(cod["cod_fee"], Decimal("49.00"))
        self.assertEqual(cod["total_amount"], Decimal("397.00"))

        upi = self.client.post(url, {"payment_method": "UPI"}, format="json").data
        self.assertEqual(upi["cod_fee"], Decimal("0.00"))
        self.assertEqual(upi["total_amount"], Decimal("348.00"))


# --------------------------------------------------------------------------
# Checkout
# --------------------------------------------------------------------------


class CheckoutTests(StoreTestBase):
    def test_checkout_is_atomic_and_snapshots_prices(self):
        self.login(self.customer)
        self.add_to_cart(quantity=2)
        address = self.make_address()
        response = self.client.post(
            reverse("store:api-orders"),
            {"address_id": address.pk, "payment_method": "COD"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        order = Order.objects.get(pk=response.data["order"]["id"])
        self.assertTrue(order.order_number.startswith("BN"))
        self.assertEqual(order.status, Order.Status.PLACED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(order.shipping_city, "Bengaluru")
        self.assertEqual(order.items.count(), 1)

        line = order.items.first()
        self.assertEqual(line.unit_price, Decimal("1999.00"))
        self.assertEqual(line.unit_mrp, Decimal("2999.00"))
        self.assertEqual(line.quantity, 2)
        self.assertEqual(line.line_saving, Decimal("2000.00"))

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        self.assertEqual(self.product.sold_count, 90)
        self.assertEqual(Cart.objects.get(user=self.customer).items.count(), 0)
        self.assertEqual(order.events.count(), 1)

        # The snapshot survives later catalogue price changes.
        Product.objects.filter(pk=self.product.pk).update(price=Decimal("1799.00"))
        line.refresh_from_db()
        self.assertEqual(line.unit_price, Decimal("1999.00"))

    def test_online_payment_is_recorded_as_paid(self):
        order = self.place_order(payment_method="UPI")
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertTrue(order.payment_reference.startswith("PAY"))

    def test_cod_fee_and_delivery_fee_are_billed(self):
        self.make_address()
        self.login(self.customer)
        self.add_to_cart(self.second)
        response = self.client.post(
            reverse("store:api-orders"),
            {"address_id": Address.objects.first().pk, "payment_method": "COD"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        order = Order.objects.get(pk=response.data["order"]["id"])
        self.assertEqual(order.subtotal, Decimal("299.00"))
        self.assertEqual(order.delivery_fee, Decimal("49.00"))
        self.assertEqual(order.cod_fee, Decimal("49.00"))
        self.assertEqual(order.total_amount, Decimal("397.00"))
        self.assertGreater(order.gst_amount, Decimal("0"))

    def test_coupon_discount_and_usage_counter(self):
        coupon = Coupon.objects.create(
            code="FLAT100",
            discount_type=Coupon.DiscountType.FLAT,
            value=Decimal("100"),
            min_order_value=Decimal("499"),
            per_user_limit=2,
        )
        order = self.place_order(coupon_code="FLAT100")
        self.assertEqual(order.discount_amount, Decimal("100.00"))
        self.assertEqual(order.coupon_code, "FLAT100")
        self.assertEqual(order.total_amount, Decimal("1948.00"))
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)

    def test_empty_cart_is_rejected(self):
        self.login(self.customer)
        address = self.make_address()
        response = self.client.post(
            reverse("store:api-orders"),
            {"address_id": address.pk, "payment_method": "COD"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("empty", response.data["detail"].lower())

    def test_stock_conflict_names_the_product_and_rolls_back(self):
        self.login(self.customer)
        self.add_to_cart(quantity=3)
        address = self.make_address()
        Product.objects.filter(pk=self.product.pk).update(stock=1)

        response = self.client.post(
            reverse("store:api-orders"),
            {"address_id": address.pk, "payment_method": "COD"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Only 1 left", response.data["detail"])
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Cart.objects.get(user=self.customer).items.count(), 1)

    def test_cod_is_blocked_above_the_cap(self):
        expensive = Product.objects.create(
            name="OLED TV 55",
            category=self.category,
            mrp=Decimal("74999.00"),
            price=Decimal("64999.00"),
            stock=3,
        )
        self.login(self.customer)
        self.add_to_cart(expensive)
        address = self.make_address()
        response = self.client.post(
            reverse("store:api-orders"),
            {"address_id": address.pk, "payment_method": "COD"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cash on Delivery", response.data["detail"])

    def test_address_must_belong_to_the_buyer(self):
        foreign = self.make_address(self.other_customer)
        self.login(self.customer)
        self.add_to_cart(self.product)
        response = self.client.post(
            reverse("store:api-orders"),
            {"address_id": foreign.pk, "payment_method": "COD"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("address_id", response.data)

    def test_delivery_eta_uses_the_slowest_of_product_and_pincode(self):
        Pincode.objects.create(
            pincode="560001", city="Bengaluru", state="Karnataka",
            eta_min_days=4, eta_max_days=6, cod_available=True,
        )
        order = self.place_order()
        expected = timezone.localdate() + datetime.timedelta(days=6)
        self.assertEqual(order.delivery_eta, expected)


# --------------------------------------------------------------------------
# Order lifecycle
# --------------------------------------------------------------------------


class OrderLifecycleTests(StoreTestBase):
    def test_customers_only_see_their_own_orders(self):
        order = self.place_order()
        url = reverse("store:api-orders")

        mine = self.client.get(url).data
        self.assertEqual(mine["count"], 1)
        self.assertFalse(mine["is_admin"])
        self.assertEqual(mine["results"][0]["id"], order.pk)

        self.login(self.other_customer)
        self.assertEqual(self.client.get(url).data["count"], 0)
        self.assertEqual(
            self.client.get(reverse("store:api-order", args=[order.pk])).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.login(self.admin)
        everything = self.client.get(url).data
        self.assertTrue(everything["is_admin"])
        self.assertEqual(everything["status_counts"]["Placed"], 1)

    def test_order_filters_by_status_and_search(self):
        order = self.place_order()
        self.login(self.customer)
        url = reverse("store:api-orders")
        self.assertEqual(self.client.get(url, {"status": "Placed"}).data["count"], 1)
        self.assertEqual(self.client.get(url, {"status": "Cancelled"}).data["count"], 0)
        self.assertEqual(
            self.client.get(url, {"q": order.order_number[:8]}).data["count"], 1
        )

    def test_cancel_restores_stock_and_refunds_online_payments(self):
        order = self.place_order(quantity=2, payment_method="UPI")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)

        response = self.client.post(
            reverse("store:api-order-cancel", args=[order.pk]),
            {"reason": "Ordered by mistake"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.REFUNDED)
        self.assertEqual(order.cancel_reason, "Ordered by mistake")
        self.assertIsNotNone(order.cancelled_at)
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(self.product.sold_count, 88)
        self.assertIn("Refund", response.data["message"])

    def test_shipped_orders_can_no_longer_be_cancelled(self):
        order = self.place_order()
        self.login(self.admin)
        for step in (Order.Status.PACKED, Order.Status.SHIPPED):
            self.client.patch(
                reverse("store:api-order-status", args=[order.pk]),
                {"status": step},
                format="json",
            )
        self.login(self.customer)
        response = self.client.post(
            reverse("store:api-order-cancel", args=[order.pk]), {}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("can no longer be cancelled", response.data["detail"])

    def test_manager_advances_the_pipeline_and_cod_settles_on_delivery(self):
        order = self.place_order()
        self.login(self.admin)
        url = reverse("store:api-order-status", args=[order.pk])

        for step in (
            Order.Status.PACKED,
            Order.Status.SHIPPED,
            Order.Status.OUT_FOR_DELIVERY,
            Order.Status.DELIVERED,
        ):
            response = self.client.patch(
                url, {"status": step, "location": "BLR hub"}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertEqual(response.data["order"]["status"], step)

        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertIsNotNone(order.delivered_at)
        self.assertEqual(order.events.count(), 5)
        self.assertIn(
            Order.Status.DELIVERED,
            [event.status for event in order.events.all()],
        )

    def test_illegal_transitions_and_duplicate_statuses_are_rejected(self):
        order = self.place_order()
        self.login(self.admin)
        url = reverse("store:api-order-status", args=[order.pk])

        jump = self.client.patch(url, {"status": "Delivered"}, format="json")
        self.assertEqual(jump.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot move", jump.data["detail"])

        self.client.patch(url, {"status": "Packed"}, format="json")
        duplicate = self.client.patch(url, {"status": "Packed"}, format="json")
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already", duplicate.data["detail"])

        invalid = self.client.patch(url, {"status": "Teleported"}, format="json")
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

    def test_customers_cannot_change_statuses(self):
        order = self.place_order()
        response = self.client.patch(
            reverse("store:api-order-status", args=[order.pk]),
            {"status": "Packed"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cancellation_marks_the_reason(self):
        order = self.place_order()
        self.login(self.admin)
        response = self.client.patch(
            reverse("store:api-order-status", args=[order.pk]),
            {"status": "Cancelled", "note": "Payment could not be verified"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.cancel_reason, "Payment could not be verified")

    def test_order_summary_counts_active_orders(self):
        self.place_order()
        second = self.place_order()
        self.client.post(reverse("store:api-order-cancel", args=[second.pk]), {}, format="json")

        data = self.client.get(reverse("store:api-order-summary")).data
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["active"], 1)
        self.assertIsNotNone(data["latest"])

    def test_invoice_renders_for_the_owner_only(self):
        order = self.place_order()
        url = reverse("store:api-order-invoice", args=[order.pk])

        self.login(None)
        anonymous = self.client.get(url)
        self.assertEqual(anonymous.status_code, status.HTTP_302_FOUND)
        self.assertIn("/login/", anonymous["Location"])

        # The invoice is a plain Django view, so it relies on the session.
        self.client.force_login(self.other_customer)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_login(self.customer)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn("TAX INVOICE", body)
        self.assertIn("GSTIN", body)
        self.assertIn(order.order_number, body)

    def test_status_stream_pushes_the_final_event(self):
        order = self.make_delivered_order()
        response = self.client.get(reverse("store:api-order-stream", args=[order.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "text/event-stream")

        chunks = iter(response.streaming_content)
        next(chunks)  # retry hint
        event = next(chunks).decode()
        self.assertIn("event: order", event)
        self.assertIn(order.order_number, event)
        response.close()


# --------------------------------------------------------------------------
# Returns
# --------------------------------------------------------------------------


class ReturnTests(StoreTestBase):
    def test_returns_require_a_delivered_order(self):
        order = self.place_order()
        response = self.client.post(
            reverse("store:api-order-return", args=[order.pk]),
            {"reason": "Damaged"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("return window", response.data["detail"])

    def test_return_request_and_refund_restore_stock(self):
        order = self.make_delivered_order(quantity=2)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)

        response = self.client.post(
            reverse("store:api-order-return", args=[order.pk]),
            {"reason": "Damaged", "comment": "Screen cracked on arrival"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return_id = response.data["return"]["id"]

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.RETURN_REQUESTED)
        self.assertEqual(
            ReturnRequest.objects.get(pk=return_id).refund_amount, order.total_amount
        )

        duplicate = self.client.post(
            reverse("store:api-order-return", args=[order.pk]),
            {"reason": "Changed mind"},
            format="json",
        )
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

        self.login(self.admin)
        listing = self.client.get(reverse("store:admin-return-list")).data
        self.assertEqual(listing["count"], 1)
        self.assertIn("customer", listing["results"][0])
        self.assertIn("order_total", listing["results"][0])

        resolved = self.client.post(
            reverse("store:admin-return-resolve", args=[return_id]),
            {"action": "refund", "admin_note": "Verified with the customer"},
            format="json",
        )
        self.assertEqual(resolved.status_code, status.HTTP_200_OK, resolved.data)

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, Order.Status.RETURNED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.REFUNDED)
        self.assertEqual(self.product.stock, 10)

    def test_rejecting_a_return_puts_the_order_back_to_delivered(self):
        order = self.make_delivered_order()
        response = self.client.post(
            reverse("store:api-order-return", args=[order.pk]),
            {"reason": "Changed mind"},
            format="json",
        )
        return_id = response.data["return"]["id"]

        self.login(self.admin)
        rejected = self.client.post(
            reverse("store:admin-return-resolve", args=[return_id]),
            {"action": "reject", "admin_note": "Outside the damage policy"},
            format="json",
        )
        self.assertEqual(rejected.status_code, status.HTTP_200_OK, rejected.data)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)

    def test_return_window_closes_after_seven_days(self):
        order = self.make_delivered_order()
        Order.objects.filter(pk=order.pk).update(
            delivered_at=timezone.now() - datetime.timedelta(days=10)
        )
        response = self.client.post(
            reverse("store:api-order-return", args=[order.pk]),
            {"reason": "Damaged"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_customers_cannot_open_the_returns_console(self):
        self.login(self.customer)
        self.assertEqual(
            self.client.get(reverse("store:admin-return-list")).status_code,
            status.HTTP_403_FORBIDDEN,
        )


# --------------------------------------------------------------------------
# Wishlist + reviews
# --------------------------------------------------------------------------


class WishlistReviewTests(StoreTestBase):
    def test_wishlist_toggles_and_lists(self):
        self.login(self.customer)
        url = reverse("store:wishlist-list")

        added = self.client.post(url, {"product": self.product.pk}, format="json")
        self.assertEqual(added.status_code, status.HTTP_200_OK)
        self.assertTrue(added.data["wishlisted"])
        self.assertEqual(added.data["count"], 1)

        listing = self.client.get(url).data
        self.assertEqual(listing["ids"], [self.product.pk])

        toggled = self.client.post(url, {"product": self.product.pk}, format="json")
        self.assertFalse(toggled.data["wishlisted"])
        self.assertEqual(toggled.data["count"], 0)

    def test_wishlist_remove_action(self):
        self.login(self.customer)
        self.client.post(
            reverse("store:wishlist-list"), {"product": self.product.pk}, format="json"
        )
        removed = self.client.delete(
            reverse("store:wishlist-remove", args=[self.product.pk])
        )
        self.assertEqual(removed.status_code, status.HTTP_200_OK)
        self.assertEqual(removed.data["count"], 0)

    def test_reviews_update_the_rating_aggregate(self):
        self.login(self.customer)
        url = reverse("store:product-reviews", args=[self.product.pk])
        response = self.client.post(
            url,
            {"rating": 4, "title": "Great bass", "body": "Excellent sound for the price."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Decimal(str(response.data["average"])), Decimal("4.0"))
        self.assertFalse(response.data["review"]["is_verified_purchase"])
        self.assertNotIn("asha", response.data["review"]["user_display"])

        self.product.refresh_from_db()
        self.assertEqual(self.product.rating_count, 1)

        duplicate = self.client.post(
            url,
            {"rating": 5, "title": "Second go", "body": "Trying to review twice here."},
            format="json",
        )
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

        listing = self.client.get(url).data
        self.assertEqual(len(listing["results"]), 1)
        self.assertEqual(listing["count"], 1)

    def test_reviews_are_marked_verified_after_a_delivered_purchase(self):
        self.make_delivered_order()
        response = self.client.post(
            reverse("store:product-reviews", args=[self.product.pk]),
            {"rating": 5, "title": "Worth every rupee", "body": "Battery easily lasts two days."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(response.data["review"]["is_verified_purchase"])

    def test_rating_out_of_range_is_rejected(self):
        self.login(self.customer)
        response = self.client.post(
            reverse("store:product-reviews", args=[self.product.pk]),
            {"rating": 6, "title": "Too generous", "body": "Ratings only go up to five."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# --------------------------------------------------------------------------
# Seller console
# --------------------------------------------------------------------------


class AdminConsoleTests(StoreTestBase):
    def test_dashboard_requires_a_manager(self):
        self.login(self.customer)
        self.assertEqual(
            self.client.get(reverse("store:api-dashboard")).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_dashboard_reports_kpis_and_feeds(self):
        order = self.place_order()
        self.login(self.admin)
        data = self.client.get(reverse("store:api-dashboard")).data

        self.assertGreaterEqual(data["kpis"]["orders"], 1)
        self.assertEqual(Decimal(data["kpis"]["revenue"]), order.total_amount)
        self.assertEqual(len(data["revenue_series"]), 14)
        self.assertEqual(data["status_counts"]["Placed"], 1)
        self.assertIn(self.second.pk, [row["id"] for row in data["low_stock"]])
        self.assertEqual(data["recent_orders"][0]["id"], order.pk)
        self.assertIn("generated_at", data)

    def test_overview_pulse_and_customers(self):
        order = self.place_order()
        self.login(self.admin)

        pulse = self.client.get(reverse("store:api-admin-overview")).data
        self.assertEqual(pulse["active"], 1)
        self.assertEqual(pulse["latest"]["order_number"], order.order_number)

        customers = self.client.get(reverse("store:api-customers")).data
        self.assertGreaterEqual(customers["count"], 2)
        spend = {
            row["username"]: Decimal(row["spend"]) for row in customers["results"]
        }
        self.assertEqual(spend["asha"], order.total_amount)

    def test_console_pages_are_admin_only(self):
        self.client.force_authenticate(user=None)
        anonymous = self.client.get(reverse("store:dashboard"))
        self.assertEqual(anonymous.status_code, status.HTTP_302_FOUND)
        self.assertIn("/login/", anonymous["Location"])

        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("store:dashboard")).status_code, 302)

        self.client.force_login(self.admin)
        for name in (
            "store:dashboard",
            "store:manage-products",
            "store:manage-orders",
            "store:manage-coupons",
            "store:manage-returns",
        ):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_coupon_console_crud(self):
        self.login(self.admin)
        url = reverse("store:admin-coupon-list")

        created = self.client.post(
            url,
            {
                "code": "save100",
                "description": "₹100 off orders above ₹499",
                "discount_type": "flat",
                "value": "100.00",
                "min_order_value": "499.00",
                "per_user_limit": 2,
            },
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertEqual(created.data["code"], "SAVE100")
        coupon_id = created.data["id"]

        duplicate = self.client.post(
            url,
            {"code": "SAVE100", "discount_type": "flat", "value": "50.00"},
            format="json",
        )
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

        paused = self.client.patch(
            reverse("store:admin-coupon-detail", args=[coupon_id]),
            {"is_active": False},
            format="json",
        )
        self.assertEqual(paused.status_code, status.HTTP_200_OK)
        self.assertFalse(paused.data["is_live"])

        removed = self.client.delete(
            reverse("store:admin-coupon-detail", args=[coupon_id])
        )
        self.assertEqual(removed.status_code, status.HTTP_200_OK)
        self.assertFalse(Coupon.objects.filter(pk=coupon_id).exists())

    def test_used_coupons_are_deactivated_not_deleted(self):
        coupon = Coupon.objects.create(
            code="USED100",
            discount_type=Coupon.DiscountType.FLAT,
            value=Decimal("100"),
            min_order_value=Decimal("0"),
        )
        self.place_order(coupon_code="USED100")
        self.login(self.admin)
        response = self.client.delete(
            reverse("store:admin-coupon-detail", args=[coupon.pk])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        coupon.refresh_from_db()
        self.assertFalse(coupon.is_active)


# --------------------------------------------------------------------------
# Cache telemetry
# --------------------------------------------------------------------------


class SystemCacheTests(StoreTestBase):
    def test_health_reports_database_and_cache(self):
        data = self.client.get(reverse("store:api-health")).data
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["database"]["ok"])
        self.assertTrue(data["cache"]["ok"])

    def test_cache_stats_track_hits_and_misses(self):
        url = reverse("store:api-cache-stats")
        before = self.client.get(url).data
        self.assertEqual(before["requests"], 0)

        products = reverse("store:product-list")
        self.client.get(products)
        self.client.get(products)

        after = self.client.get(url).data
        self.assertGreaterEqual(after["hits"], 1)
        self.assertGreaterEqual(after["misses"], 1)
        self.assertGreaterEqual(after["hit_rate"], 0)
        self.assertIn("product_list", after["ttls"])
        self.assertEqual(after["catalog_version"], before["catalog_version"])

    def test_simulate_shows_miss_then_hit(self):
        url = reverse("store:api-simulate")
        miss = self.client.post(url, {"probe": "suite"}, format="json").data
        self.assertFalse(miss["hit"])
        self.assertEqual(
            [step["id"] for step in miss["steps"]],
            ["browser", "cache", "database", "backfill"],
        )
        self.assertEqual(miss["steps"][1]["state"], "miss")

        hit = self.client.post(url, {"probe": "suite"}, format="json").data
        self.assertTrue(hit["hit"])
        states = {step["id"]: step["state"] for step in hit["steps"]}
        self.assertEqual(states["cache"], "hit")
        self.assertEqual(states["database"], "skipped")

    def test_cache_reset_invalidates_the_catalog_namespace(self):
        products = reverse("store:product-list")
        self.client.get(products)
        self.assertEqual(self.client.get(products)["X-Cache"], "HIT")

        reset = self.client.post(reverse("store:api-cache-reset"))
        self.assertEqual(reset.status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(products)["X-Cache"], "MISS")

    def test_cache_warm_fills_known_namespaces(self):
        data = self.client.post(reverse("store:api-cache-warm")).data
        self.assertGreaterEqual(len(data["keys"]), 3)
        self.assertTrue(data["backend"])


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------


class PageTests(StoreTestBase):
    def test_public_pages_render(self):
        for url in (
            reverse("store:home"),
            reverse("store:shop"),
            reverse("store:product", args=[self.product.slug]),
            reverse("store:offers"),
            reverse("store:architecture"),
            reverse("store:login"),
            reverse("store:register"),
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_customer_pages_redirect_anonymous_visitors(self):
        for name in (
            "store:cart",
            "store:checkout",
            "store:orders",
            "store:wishlist",
            "store:account",
        ):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn("/login/?next=", response["Location"])

    def test_customer_pages_render_when_signed_in(self):
        self.client.force_login(self.customer)
        order = self.place_order()
        for name in ("store:cart", "store:checkout", "store:orders", "store:wishlist", "store:account"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.assertEqual(
            self.client.get(reverse("store:order-detail", args=[order.pk])).status_code,
            200,
        )
