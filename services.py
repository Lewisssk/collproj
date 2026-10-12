from __future__ import annotations

from money import Money
from models import CartItem, Order, OrderStatus, Product
from exceptions import (
    EmptyCart,
    InvalidQuantity,
    PaymentFailed,
    ProductNotFound,
    PromoCodeExpired,
)
from repositories import (
    PriceRepository,
    DiscountService,
    ShippingCalculator,
    PaymentGateway,
)

# --- Бизнес-константы ---
BULK_DISCOUNT_THRESHOLD = Money.of("1000")   # subtotal > 1000 → 10%
BULK_DISCOUNT_RATE = 0.10
SAVE10_RATE = 0.10
SAVE10_MAX = Money.of("500")
FREE_SHIPPING_THRESHOLD = Money.of("3000")   # после скидки
FIXED_SHIPPING = Money.of("300")

VALID_PROMO_CODES = {"SAVE10"}      # активные
EXPIRED_PROMO_CODES = {"OLD10"}     # просроченные


class Cart:
    def __init__(self, price_repository: PriceRepository):
        self._price_repo = price_repository
        self._items: dict[str, CartItem] = {}  # product_id -> CartItem

    # --- публичный контракт ---
    def add_item(self, product_id: str, quantity: int) -> None:
        self._validate_quantity(quantity)
        price = self._price_repo.get_price(product_id)  # ProductNotFound пробросится
        if product_id in self._items:
            # повторное добавление увеличивает количество
            self._items[product_id].quantity += quantity
        else:
            self._items[product_id] = CartItem(
                product_id=product_id, quantity=quantity, price=price
            )

    def remove_item(self, product_id: str) -> None:
        # Решение: удаление несуществующего — no-op (зафиксировано в тестах)
        self._items.pop(product_id, None)

    def change_quantity(self, product_id: str, quantity: int) -> None:
        self._validate_quantity(quantity)
        if product_id not in self._items:
            raise ProductNotFound(product_id)
        self._items[product_id].quantity = quantity

    def get_items(self) -> list[CartItem]:
        return list(self._items.values())

    def subtotal(self) -> Money:
        total = Money.zero()
        for item in self._items.values():
            total = total + item.line_total()
        return total

    def clear(self) -> None:
        self._items.clear()

    def is_empty(self) -> bool:
        return not self._items

    # --- внутреннее ---
    @staticmethod
    def _validate_quantity(quantity: int) -> None:
        if not isinstance(quantity, int) or isinstance(quantity, bool):
            raise InvalidQuantity(quantity)
        if quantity <= 0:
            raise InvalidQuantity(quantity)


# ---------------------------------------------------------------------------
# Реализации DiscountService / ShippingCalculator (можно использовать в проде)
# ---------------------------------------------------------------------------
class DefaultDiscountService:
    def apply(self, cart: Cart, promo_code: str | None) -> Money:
        subtotal = cart.subtotal()
        discount = Money.zero()

        # 1) Базовая скидка 10% при subtotal > 1000
        if subtotal > BULK_DISCOUNT_THRESHOLD:
            discount = subtotal.percent(BULK_DISCOUNT_RATE)

        # 2) Промокод SAVE10: ещё 10%, но не больше 500.
        if promo_code is not None:
            if promo_code in EXPIRED_PROMO_CODES:
                raise PromoCodeExpired(promo_code)
            if promo_code in VALID_PROMO_CODES:
                promo_discount = subtotal.percent(SAVE10_RATE)
                if promo_discount > SAVE10_MAX:
                    promo_discount = SAVE10_MAX
                discount = discount + promo_discount
            # неизвестный код — просто игнорируем (можно ужесточить при желании)

        # Скидка не может превышать subtotal
        if discount > subtotal:
            discount = subtotal
        return discount


class DefaultShippingCalculator:
    def calculate(self, cart_total: Money, address: str) -> Money:
        if cart_total >= FREE_SHIPPING_THRESHOLD:
            return Money.zero()
        return FIXED_SHIPPING


# ---------------------------------------------------------------------------
# OrderService
# ---------------------------------------------------------------------------
class OrderService:
    def __init__(
        self,
        price_repository: PriceRepository,
        discount_service: DiscountService,
        shipping_calculator: ShippingCalculator,
        payment_gateway: PaymentGateway,
    ):
        self._price_repo = price_repository
        self._discount = discount_service
        self._shipping = shipping_calculator
        self._payment = payment_gateway

    def checkout(
        self,
        cart: Cart,
        promo_code: str | None,
        address: str,
        payment_method: str,
    ) -> Order:
        if cart.is_empty():
            raise EmptyCart()

        subtotal = cart.subtotal()
        discount = self._discount.apply(cart, promo_code)
        after_discount = subtotal - discount
        shipping = self._shipping.calculate(after_discount, address)
        total = after_discount + shipping

        paid = self._payment.charge(total, payment_method)
        if not paid:
            # корзина НЕ очищается, заказ НЕ создаётся
            raise PaymentFailed()

        order = Order(
            items=cart.get_items(),
            subtotal=subtotal,
            discount=discount,
            shipping=shipping,
            total=total,
            status=OrderStatus.PAID,
        )
        cart.clear()
        return order