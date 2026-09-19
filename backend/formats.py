"""Formatage monétaire belge : 1.234,56 (point = milliers, virgule = décimales)."""
from decimal import Decimal


def eur_be(x) -> str:
    x = Decimal(x)
    neg = x < 0
    s = f"{abs(x):,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return ("-" if neg else "") + s
