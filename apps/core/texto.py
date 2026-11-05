"""Comparación de textos."""
from difflib import SequenceMatcher

from django.utils.text import slugify

SIMILITUD_MINIMA = 0.75


def se_parecen(uno, otro):
    a, b = slugify(uno), slugify(otro)
    if not a or not b:
        return uno.strip().lower() == otro.strip().lower()
    return a in b or b in a or SequenceMatcher(None, a, b).ratio() >= SIMILITUD_MINIMA
