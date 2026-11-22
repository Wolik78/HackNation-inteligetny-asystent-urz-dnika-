"""Wspólne instancje usług używane przez interfejs."""

from .ai import BielikService, Urzedus
from .archiwum import Archiwum
from .konfiguracja import KATALOG_DANYCH
from .pliki import MagazynPlikow

magazyn = MagazynPlikow(KATALOG_DANYCH)
bielik = BielikService()
archiwum = Archiwum(magazyn, bielik)
urzedus = Urzedus(bielik, szukaj_podobnych=archiwum.szukaj)
