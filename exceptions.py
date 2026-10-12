class CartError(Exception):
    """Базовое исключение домена."""


class InvalidQuantity(CartError): pass

class ProductNotFound(CartError): pass

class PromoCodeExpired(CartError): pass

class EmptyCart(CartError): pass

class PaymentFailed(CartError): pass