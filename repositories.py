from __future__ import annotations
from typing import Protocol

from money import Money


class PriceRepository(Protocol):
    def get_price(self, product_id: str) -> Money: ...


class DiscountService(Protocol):
    def apply(self, cart, promo_code: str | None) -> Money: ...


class ShippingCalculator(Protocol):
    def calculate(self, cart_total: Money, address: str) -> Money: ...


class PaymentGateway(Protocol):
    def charge(self, amount: Money, payment_method: str) -> bool: ...