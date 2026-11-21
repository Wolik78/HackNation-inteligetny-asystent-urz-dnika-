"""Wspólne instancje usług używane przez interfejs."""

from .konfiguracja import KATALOG_DANYCH
from .pliki import MagazynPlikow

magazyn = MagazynPlikow(KATALOG_DANYCH)
