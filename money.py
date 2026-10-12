from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass


@dataclass(frozen=True)
class Money:
    """Деньги. Внутри — Decimal с 2 знаками, округление half-up."""
    amount: Decimal

    def __post_init__(self):
        # Приводим к 2 знакам через half-up сразу при создании
        object.__setattr__(
            self,
            "amount",
            self.amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        )

    def __add__(self, other: "Money") -> "Money":
        return Money(self.amount + other.amount)

    def __sub__(self, other: "Money") -> "Money":
        return Money(self.amount - other.amount)

    def __mul__(self, factor: int | Decimal) -> "Money":
        return Money(self.amount * Decimal(factor))

    def __lt__(self, other: "Money") -> bool:
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        return self.amount <= other.amount

    def __ge__(self, other: "Money") -> bool:
        return self.amount >= other.amount

    def __gt__(self, other: "Money") -> bool:
        return self.amount > other.amount

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Money) and self.amount == other.amount

    def __repr__(self) -> str:
        return f"Money({self.amount})"

    @classmethod
    def zero(cls) -> "Money":
        return cls(Decimal("0"))

    @classmethod
    def of(cls, value: str | int | Decimal) -> "Money":
        return cls(Decimal(str(value)))

    def percent(self, pct: Decimal | float | int) -> "Money":
        """pct — доля, напр. 0.10 для 10%. Принимает Decimal/float/int."""
        if not isinstance(pct, Decimal):
            pct = Decimal(str(pct))   # str() обязателен, иначе 0.1 → 0.1000000000000000055...
        return Money(self.amount * pct)