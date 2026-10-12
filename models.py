from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

from money import Money


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    price: Money


@dataclass
class CartItem:
    product_id: str
    quantity: int
    price: Money  # цена за единицу, зафиксирована на момент добавления

    def line_total(self) -> Money:
        return self.price * self.quantity


class OrderStatus(str, Enum):
    CREATED = "created"
    PAID = "paid"
    FAILED = "failed"


@dataclass
class Order:
    items: list[CartItem]
    subtotal: Money
    discount: Money
    shipping: Money
    total: Money
    status: OrderStatus = OrderStatus.CREATED