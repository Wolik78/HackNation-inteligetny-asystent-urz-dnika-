"""Wspólne instancje usług używane przez interfejs."""

from .ai import BielikService, Urzedus
from .konfiguracja import KATALOG_DANYCH
from .pliki import MagazynPlikow

magazyn = MagazynPlikow(KATALOG_DANYCH)
bielik = BielikService()
urzedus = Urzedus(bielik)
