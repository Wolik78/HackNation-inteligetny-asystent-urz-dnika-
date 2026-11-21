"""Ekrany aplikacji – każdy w osobnym module."""

from .archiwum import strona_archiwum
from .baza_wiedzy import strona_baza_wiedzy
from .nowy_wniosek import strona_nowy_wniosek
from .sprawa import strona_sprawa
from .ustawienia import strona_ustawienia
from .wnioski import strona_wnioski

__all__ = ['strona_archiwum', 'strona_baza_wiedzy', 'strona_nowy_wniosek', 'strona_sprawa',
           'strona_ustawienia', 'strona_wnioski']
