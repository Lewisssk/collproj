from decimal import Decimal

import pytest

from money import Money
from models import Product
from exceptions import (
    EmptyCart,
    InvalidQuantity,
    PaymentFailed,
    ProductNotFound,
    PromoCodeExpired,
)
from services import (
    Cart,
    DefaultDiscountService,
    DefaultShippingCalculator,
    OrderService,
    SAVE10_MAX,
)


# ---------------------------------------------------------------------------
# Стабы и моки
# ---------------------------------------------------------------------------
class StubPriceRepository:
    """Стаб: возвращает заранее заданные цены."""
    def __init__(self, prices: dict[str, str]):
        self._prices = {pid: Money.of(p) for pid, p in prices.items()}

    def get_price(self, product_id: str) -> Money:
        if product_id not in self._prices:
            raise ProductNotFound(product_id)
        return self._prices[product_id]


class SpyPaymentGateway:
    """Мок: запоминает вызовы charge, возвращает заданный результат."""
    def __init__(self, succeed: bool = True):
        self.succeed = succeed
        self.calls: list[tuple[Money, str]] = []

    def charge(self, amount: Money, payment_method: str) -> bool:
        self.calls.append((amount, payment_method))
        return self.succeed


class StubDiscountService:
    """Простой стаб скидки — можно подменять поведение в тестах."""
    def __init__(self, value: str = "0"):
        self._value = Money.of(value)

    def apply(self, cart, promo_code):
        return self._value


class StubShippingCalculator:
    def __init__(self, value: str = "0"):
        self._value = Money.of(value)

    def calculate(self, cart_total, address):
        return self._value


@pytest.fixture
def price_repo():
    return StubPriceRepository({
        "apple": "100",
        "banana": "50",
        "tv": "2000",
    })


@pytest.fixture
def cart(price_repo):
    return Cart(price_repo)


# ---------------------------------------------------------------------------
# Money / округление
# ---------------------------------------------------------------------------
def test_money_rounding_half_up():
    # 0.005 → 0.01 (half-up), не bankers rounding
    assert Money.of("0.005") == Money.of("0.01")
    assert Money.of("0.004") == Money.of("0.00")
    assert Money.of("1.005") == Money.of("1.01")


def test_money_no_float_usage():
    # Демонстрация: float нельзя передавать в Decimal без str()
    assert Money.of("0.1") + Money.of("0.2") == Money.of("0.3")


# ---------------------------------------------------------------------------
# Cart: quantity
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad_qty", [0, -1, -100])
def test_add_item_invalid_quantity(cart, bad_qty):
    with pytest.raises(InvalidQuantity):
        cart.add_item("apple", bad_qty)


def test_add_item_positive_quantity(cart):
    cart.add_item("apple", 3)
    items = cart.get_items()
    assert len(items) == 1
    assert items[0].quantity == 3
    assert items[0].price == Money.of("100")


def test_add_same_item_increases_quantity(cart):
    cart.add_item("apple", 2)
    cart.add_item("apple", 3)
    items = cart.get_items()
    assert len(items) == 1
    assert items[0].quantity == 5


def test_add_item_unknown_product(cart):
    with pytest.raises(ProductNotFound):
        cart.add_item("unknown", 1)


# ---------------------------------------------------------------------------
# Cart: remove
# ---------------------------------------------------------------------------
def test_remove_existing_item(cart):
    cart.add_item("apple", 1)
    cart.remove_item("apple")
    assert cart.get_items() == []


def test_remove_nonexistent_is_noop(cart):
    # Зафиксированное решение: no-op
    cart.remove_item("nonexistent")
    assert cart.get_items() == []


# ---------------------------------------------------------------------------
# Cart: change_quantity
# ---------------------------------------------------------------------------
def test_change_quantity(cart):
    cart.add_item("apple", 1)
    cart.change_quantity("apple", 10)
    assert cart.get_items()[0].quantity == 10


def test_change_quantity_invalid(cart):
    cart.add_item("apple", 1)
    with pytest.raises(InvalidQuantity):
        cart.change_quantity("apple", 0)


def test_change_quantity_unknown(cart):
    with pytest.raises(ProductNotFound):
        cart.change_quantity("ghost", 5)


# ---------------------------------------------------------------------------
# Cart: subtotal, clear
# ---------------------------------------------------------------------------
def test_subtotal(cart):
    cart.add_item("apple", 2)   # 200
    cart.add_item("banana", 3)  # 150
    assert cart.subtotal() == Money.of("350")


def test_clear(cart):
    cart.add_item("apple", 1)
    cart.clear()
    assert cart.get_items() == []
    assert cart.subtotal() == Money.zero()


# ---------------------------------------------------------------------------
# Скидки
# ---------------------------------------------------------------------------
def test_no_discount_below_threshold(price_repo):
    cart = Cart(price_repo)
    cart.add_item("apple", 5)  # 500
    discount = DefaultDiscountService().apply(cart, None)
    assert discount == Money.of("0")


def test_bulk_discount_over_1000(price_repo):
    cart = Cart(price_repo)
    cart.add_item("tv", 1)  # 2000
    discount = DefaultDiscountService().apply(cart, None)
    assert discount == Money.of("200")  # 10%


def test_save10_discount(price_repo):
    cart = Cart(price_repo)
    cart.add_item("apple", 5)  # 500 (нет bulk)
    discount = DefaultDiscountService().apply(cart, "SAVE10")
    assert discount == Money.of("50")


def test_save10_capped_at_500(price_repo):
    cart = Cart(price_repo)
    cart.add_item("tv", 10)  # 20000
    # bulk 10% = 2000 + save10 10% = 2000 → capped 500 → итого 2500? 
    # По правилам: bulk + promo, promo ≤ 500.
    discount = DefaultDiscountService().apply(cart, "SAVE10")
    # bulk 2000 + promo min(2000, 500)=500 → 2500
    assert discount == Money.of("2500")
    # проверим, что только promo часть ограничена
    promo_only = DefaultDiscountService().apply(cart, None)
    assert discount - promo_only == SAVE10_MAX


def test_expired_promo(price_repo):
    cart = Cart(price_repo)
    cart.add_item("apple", 5)
    with pytest.raises(PromoCodeExpired):
        DefaultDiscountService().apply(cart, "OLD10")


# ---------------------------------------------------------------------------
# Доставка
# ---------------------------------------------------------------------------
def test_free_shipping_over_3000():
    calc = DefaultShippingCalculator()
    assert calc.calculate(Money.of("3000"), "Moscow") == Money.zero()
    assert calc.calculate(Money.of("5000"), "Moscow") == Money.zero()


def test_fixed_shipping_below_3000():
    calc = DefaultShippingCalculator()
    assert calc.calculate(Money.of("2999.99"), "Moscow") == Money.of("300")


# ---------------------------------------------------------------------------
# OrderService: happy path
# ---------------------------------------------------------------------------
def test_checkout_success_clears_cart_and_charges(price_repo):
    cart = Cart(price_repo)
    cart.add_item("tv", 1)  # 2000, bulk discount 200 → 1800 (>=3000? нет)
    payment = SpyPaymentGateway(succeed=True)
    service = OrderService(
        price_repository=price_repo,
        discount_service=DefaultDiscountService(),
        shipping_calculator=DefaultShippingCalculator(),
        payment_gateway=payment,
    )
    order = service.checkout(cart, None, "Moscow", "card")

    assert order.subtotal == Money.of("2000")
    assert order.discount == Money.of("200")
    assert order.shipping == Money.of("300")  # 1800 < 3000
    assert order.total == Money.of("2100")
    assert order.status.value == "paid"

    # проверяем, что charge вызван с нужной суммой
    assert len(payment.calls) == 1
    assert payment.calls[0] == (Money.of("2100"), "card")

    # корзина очищена
    assert cart.is_empty()


def test_checkout_free_shipping(price_repo):
    cart = Cart(price_repo)
    cart.add_item("tv", 5)  # 10000, bulk 1000 → 9000 (>=3000 → free)
    payment = SpyPaymentGateway()
    service = OrderService(
        price_repo, DefaultDiscountService(),
        DefaultShippingCalculator(), payment,
    )
    order = service.checkout(cart, None, "Moscow", "card")
    assert order.shipping == Money.zero()
    assert order.total == Money.of("9000")


# ---------------------------------------------------------------------------
# OrderService: ошибки
# ---------------------------------------------------------------------------
def test_checkout_empty_cart(price_repo):
    cart = Cart(price_repo)
    service = OrderService(
        price_repo, DefaultDiscountService(),
        DefaultShippingCalculator(), SpyPaymentGateway(),
    )
    with pytest.raises(EmptyCart):
        service.checkout(cart, None, "Moscow", "card")


def test_checkout_payment_failed_keeps_cart(price_repo):
    cart = Cart(price_repo)
    cart.add_item("apple", 1)
    payment = SpyPaymentGateway(succeed=False)
    service = OrderService(
        price_repo, DefaultDiscountService(),
        DefaultShippingCalculator(), payment,
    )
    with pytest.raises(PaymentFailed):
        service.checkout(cart, None, "Moscow", "card")

    # корзина НЕ очищена
    assert not cart.is_empty()
    # попытка списания была
    assert len(payment.calls) == 1


# ---------------------------------------------------------------------------
# OrderService: изоляция через стабы
# ---------------------------------------------------------------------------
def test_checkout_uses_injected_discount_and_shipping(price_repo):
    cart = Cart(price_repo)
    cart.add_item("apple", 1)  # 100

    payment = SpyPaymentGateway()
    service = OrderService(
        price_repository=price_repo,
        discount_service=StubDiscountService("10"),
        shipping_calculator=StubShippingCalculator("50"),
        payment_gateway=payment,
    )
    order = service.checkout(cart, None, "X", "cash")
    assert order.discount == Money.of("10")
    assert order.shipping == Money.of("50")
    assert order.total == Money.of("140")
    assert payment.calls[0][0] == Money.of("140")