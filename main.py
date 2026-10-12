# demo.py
from money import Money
from exceptions import ProductNotFound, PaymentFailed, EmptyCart
from services import (
    Cart,
    DefaultDiscountService,
    DefaultShippingCalculator,
    OrderService,
)


class InMemoryPriceRepository:
    def __init__(self, prices: dict[str, str]):
        self._prices = {k: Money.of(v) for k, v in prices.items()}

    def get_price(self, product_id: str) -> Money:
        if product_id not in self._prices:
            raise ProductNotFound(product_id)
        return self._prices[product_id]


class PrintPaymentGateway:
    def charge(self, amount: Money, payment_method: str) -> bool:
        print(f"  [PAYMENT] Списываем {amount} через '{payment_method}'")
        return True  # всегда успех


def main():
    repo = InMemoryPriceRepository({
        "apple": "100",
        "tv": "2000",
        "book": "350",
    })

    cart = Cart(repo)
    cart.add_item("apple", 3)   # 300
    cart.add_item("book", 2)    # 700
    cart.add_item("tv", 1)      # 2000
    # subtotal = 3000

    print("Корзина:")
    for item in cart.get_items():
        print(f"  {item.product_id}: {item.quantity} × {item.price} = {item.line_total()}")
    print(f"Subtotal: {cart.subtotal()}")

    service = OrderService(
        price_repository=repo,
        discount_service=DefaultDiscountService(),
        shipping_calculator=DefaultShippingCalculator(),
        payment_gateway=PrintPaymentGateway(),
    )

    try:
        order = service.checkout(cart, promo_code="SAVE10", address="Moscow", payment_method="card")
        print("\nЗаказ создан:")
        print(f"  Subtotal:  {order.subtotal}")
        print(f"  Discount:  {order.discount}")
        print(f"  Shipping:  {order.shipping}")
        print(f"  Total:     {order.total}")
        print(f"  Status:    {order.status.value}")
        print(f"  Корзина пуста после checkout: {cart.is_empty()}")
    except EmptyCart:
        print("Корзина пуста!")
    except PaymentFailed:
        print("Оплата не прошла, корзина сохранена")


if __name__ == "__main__":
    main()