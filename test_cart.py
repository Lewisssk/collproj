import pytest
from decimal import Decimal

from money import Money
from exceptions import InvalidQuantity, PromoCodeExpired, PaymentFailed
from services import (
    Cart,
    OrderService,
    DefaultDiscountService,
    DefaultShippingCalculator,
    VALID_PROMO_CODES,
    EXPIRED_PROMO_CODES,
)


class StubPriceRepository:
    def __init__(self, prices: dict[str, str]):
        self._prices = {pid: Money.of(p) for pid, p in prices.items()}
    def get_price(self, product_id: str) -> Money:
        return self._prices.get(product_id, Money.zero())

class SpyPaymentGateway:
    def __init__(self, succeed: bool = True):
        self.succeed = succeed
        self.calls = []
    def charge(self, amount: Money, payment_method: str) -> bool:
        self.calls.append((amount, payment_method))
        return self.succeed

class StubShippingCalculator:
    """Заглушка доставки для тестов, где доставка не проверяется."""
    def calculate(self, cart_total: Money, address: str) -> Money:
        return Money.zero()

@pytest.fixture
def price_repo():
    return StubPriceRepository({"item": "500", "item_1001": "1001", "item_5000": "5000"})

@pytest.fixture
def cart(price_repo):
    return Cart(price_repo)

def test_1_empty_cart_subtotal(cart):
    assert cart.subtotal() == Money.zero()

def test_2_add_item_quantity_and_sum(cart):
    cart.add_item("item", 2)
    items = cart.get_items()
    assert items[0].quantity == 2
    assert cart.subtotal() == Money.of("1000")

def test_3_add_negative_quantity(cart):
    with pytest.raises(InvalidQuantity):
        cart.add_item("item", -1)

def test_4_change_quantity_to_zero(cart):
    cart.add_item("item", 1)
    with pytest.raises(InvalidQuantity):
        cart.change_quantity("item", 0)

def test_5_no_discount_at_subtotal_1000(cart):
    cart.add_item("item", 2) # 500 * 2 = 1000
    discount = DefaultDiscountService().apply(cart, None)
    assert discount == Money.zero()

def test_6_discount_applied_at_subtotal_1001(cart):
    cart.add_item("item_1001", 1)
    discount = DefaultDiscountService().apply(cart, None)
    assert discount == Money.of("100.10") # 10% от 1001

def test_7_promo_save10_max_500(cart):
    cart.add_item("item_5000", 1) # 5000. Базовая скидка 10% = 500.
    discount = DefaultDiscountService().apply(cart, "SAVE10")
    assert discount == Money.of("1000")

def test_8_expired_promo(cart):
    cart.add_item("item", 1)
    with pytest.raises(PromoCodeExpired):
        DefaultDiscountService().apply(cart, "OLD10")

def test_9_free_shipping_at_3000():
    calc = DefaultShippingCalculator()
    assert calc.calculate(Money.of("3000"), "address") == Money.zero()

def test_10_paid_shipping_at_2999():
    calc = DefaultShippingCalculator()
    assert calc.calculate(Money.of("2999"), "address") == Money.of("300")

def test_11_checkout_success(price_repo, cart):
    cart.add_item("item", 1)
    service = OrderService(
        price_repository=price_repo,
        discount_service=DefaultDiscountService(),
        shipping_calculator=StubShippingCalculator(),
        payment_gateway=SpyPaymentGateway(succeed=True)
    )
    order = service.checkout(cart, None, "address", "card")
    assert order is not None
    assert cart.is_empty()

def test_12_checkout_payment_failed(price_repo, cart):
    cart.add_item("item", 1)
    service = OrderService(
        price_repository=price_repo,
        discount_service=DefaultDiscountService(),
        shipping_calculator=StubShippingCalculator(),
        payment_gateway=SpyPaymentGateway(succeed=False)
    )
    with pytest.raises(PaymentFailed):
        service.checkout(cart, None, "address", "card")
    assert not cart.is_empty()

def test_13_payment_gateway_charge_called_once_with_correct_amount(price_repo, cart):
    cart.add_item("item", 1) # Товар 500
    payment_mock = SpyPaymentGateway(succeed=True)
    service = OrderService(
        price_repository=price_repo,
        discount_service=DefaultDiscountService(),
        shipping_calculator=DefaultShippingCalculator(), # Доставка 300 (т.к. < 3000)
        payment_gateway=payment_mock
    )
    service.checkout(cart, None, "address", "card")
    
    # Проверяем, что вызов ровно один
    assert len(payment_mock.calls) == 1
    
    # Проверяем сумму: 500 (товар) + 300 (доставка) = 800
    charged_amount, _ = payment_mock.calls[0]
    assert charged_amount == Money.of("800")