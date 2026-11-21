"""Drobne narzędzia tekstowe wspólne dla modułów AI."""

import unicodedata


def normalizuj(tekst: str) -> str:
    """Małe litery bez polskich znaków – żeby „streść” i „stresc” znaczyły to samo."""
    tekst = tekst.lower().replace('ł', 'l')
    return ''.join(z for z in unicodedata.normalize('NFKD', tekst) if not unicodedata.combining(z))
