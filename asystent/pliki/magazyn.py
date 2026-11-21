"""Lokalny magazyn dokumentów.

Układ katalogów (wszystko w KATALOG_DANYCH, poza repozytorium):

    przychodzace/                      wnioski wgrane, jeszcze niezatwierdzone
    sprawy/<nr sprawy>/wniosek/        plik wniosku
    sprawy/<nr sprawy>/odpowiedzi/     odpowiedzi z wydziałów
    sprawy/<nr sprawy>/eksport/        wygenerowane pisma
    baza_wiedzy/ustawy|zarzadzenia|archiwum/

Obok każdego pliku leżą:
    <plik>.meta.json   – metadane (oryginalna nazwa, SHA-256, data, ostrzeżenia…)
    <plik>.tekst.txt   – tekst wyciągnięty z dokumentu (do wyszukiwania i AI)
"""

import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from .ekstrakcja import wyciagnij_tekst
from .walidacja import bezpieczna_nazwa, sprawdz_plik

ROZSZERZENIE_META = '.meta.json'
ROZSZERZENIE_TEKSTU = '.tekst.txt'


class Kategoria(StrEnum):
    WNIOSEK = 'wniosek'
    ODPOWIEDZ_WYDZIALU = 'odpowiedzi'
    USTAWA = 'ustawy'
    ZARZADZENIE = 'zarzadzenia'
    ARCHIWUM = 'archiwum'

    @property
    def etykieta(self) -> str:
        return {
            Kategoria.WNIOSEK: 'Wniosek',
            Kategoria.ODPOWIEDZ_WYDZIALU: 'Odpowiedź wydziału',
            Kategoria.USTAWA: 'Ustawa',
            Kategoria.ZARZADZENIE: 'Zarządzenie',
            Kategoria.ARCHIWUM: 'Archiwalna odpowiedź',
        }[self]

    @property
    def dotyczy_sprawy(self) -> bool:
        return self in (Kategoria.WNIOSEK, Kategoria.ODPOWIEDZ_WYDZIALU)


KATEGORIE_BAZY_WIEDZY = (Kategoria.USTAWA, Kategoria.ZARZADZENIE, Kategoria.ARCHIWUM)


@dataclass
class ZapisanyPlik:
    plik: str                   # nazwa pliku na dysku (w katalogu kategorii)
    nazwa_oryginalna: str
    kategoria: Kategoria
    sprawa: str | None
    rozmiar: int
    sha256: str
    dodano: str                 # ISO 8601
    liczba_stron: int | None
    liczba_znakow: int
    ostrzezenia: list[str] = field(default_factory=list)
    opis: str | None = None     # np. wydział, od którego przyszła odpowiedź

    katalog: Path = field(default=Path(), repr=False, compare=False)
    duplikat: bool = field(default=False, compare=False)  # True, jeśli identyczny plik już był

    @property
    def sciezka(self) -> Path:
        return self.katalog / self.plik

    @property
    def sciezka_meta(self) -> Path:
        return self.katalog / (self.plik + ROZSZERZENIE_META)

    @property
    def sciezka_tekstu(self) -> Path:
        return self.katalog / (self.plik + ROZSZERZENIE_TEKSTU)

    @property
    def typ(self) -> str:
        return Path(self.plik).suffix.lstrip('.').upper()

    @property
    def data_dodania(self) -> datetime:
        return datetime.fromisoformat(self.dodano)

    def tekst(self) -> str:
        return self.sciezka_tekstu.read_text('utf-8') if self.sciezka_tekstu.exists() else ''

    def _zapisz_meta(self) -> None:
        dane = asdict(self)
        for pole in ('katalog', 'duplikat'):
            dane.pop(pole)
        self.sciezka_meta.write_text(json.dumps(dane, ensure_ascii=False, indent=2), 'utf-8')

    @classmethod
    def _wczytaj(cls, sciezka_meta: Path) -> 'ZapisanyPlik':
        dane = json.loads(sciezka_meta.read_text('utf-8'))
        dane['kategoria'] = Kategoria(dane['kategoria'])
        return cls(**dane, katalog=sciezka_meta.parent)


class MagazynPlikow:
    def __init__(self, katalog: Path) -> None:
        self.katalog = Path(katalog)

    # --- ścieżki ---

    def katalog_sprawy(self, sprawa: str) -> Path:
        return self.katalog / 'sprawy' / _bezpieczny_nr(sprawa)

    def katalog_eksportu(self, sprawa: str) -> Path:
        return self.katalog_sprawy(sprawa) / 'eksport'

    def _katalog(self, kategoria: Kategoria, sprawa: str | None) -> Path:
        if kategoria.dotyczy_sprawy:
            if sprawa is None:
                if kategoria is not Kategoria.WNIOSEK:
                    raise ValueError('Odpowiedź wydziału musi być przypisana do sprawy.')
                return self.katalog / 'przychodzace'
            return self.katalog_sprawy(sprawa) / kategoria.value
        return self.katalog / 'baza_wiedzy' / kategoria.value

    # --- operacje ---

    def zapisz(self, dane: bytes, nazwa: str, kategoria: Kategoria, *,
               sprawa: str | None = None, opis: str | None = None) -> ZapisanyPlik:
        """Waliduje plik, zapisuje go, wyciąga tekst i metadane.

        Rzuca BladPliku, jeśli pliku nie można przyjąć albo odczytać (nic wtedy nie zostaje na dysku).
        Jeśli identyczny plik już jest w tym miejscu, zwraca istniejący z duplikat=True.
        """
        sprawdz_plik(nazwa, dane)
        katalog = self._katalog(kategoria, sprawa)
        sha256 = hashlib.sha256(dane).hexdigest()

        for istniejacy in self._wczytaj_katalog(katalog):
            if istniejacy.sha256 == sha256:
                istniejacy.duplikat = True
                return istniejacy

        katalog.mkdir(parents=True, exist_ok=True)
        teraz = datetime.now()
        sciezka = _unikalna_sciezka(katalog, f'{teraz:%Y%m%d-%H%M%S}_{bezpieczna_nazwa(nazwa)}')
        sciezka.write_bytes(dane)

        try:
            wynik = wyciagnij_tekst(sciezka)
        except Exception:
            sciezka.unlink(missing_ok=True)
            raise

        plik = ZapisanyPlik(
            plik=sciezka.name,
            nazwa_oryginalna=nazwa,
            kategoria=kategoria,
            sprawa=sprawa,
            rozmiar=len(dane),
            sha256=sha256,
            dodano=teraz.isoformat(timespec='seconds'),
            liczba_stron=wynik.liczba_stron,
            liczba_znakow=len(wynik.tekst),
            ostrzezenia=wynik.ostrzezenia,
            opis=opis,
            katalog=katalog,
        )
        plik.sciezka_tekstu.write_text(wynik.tekst, 'utf-8')
        plik._zapisz_meta()
        return plik

    def lista(self, kategoria: Kategoria, sprawa: str | None = None) -> list[ZapisanyPlik]:
        """Pliki danej kategorii, od najstarszych."""
        return self._wczytaj_katalog(self._katalog(kategoria, sprawa))

    def przenies_do_sprawy(self, plik: ZapisanyPlik, sprawa: str) -> ZapisanyPlik:
        """Przenosi wniosek z „przychodzących” do katalogu zatwierdzonej sprawy."""
        cel = self._katalog(plik.kategoria, sprawa)
        cel.mkdir(parents=True, exist_ok=True)
        nowa_sciezka = _unikalna_sciezka(cel, plik.plik)
        for zrodlo, nazwa_celu in [
            (plik.sciezka, nowa_sciezka.name),
            (plik.sciezka_tekstu, nowa_sciezka.name + ROZSZERZENIE_TEKSTU),
        ]:
            if zrodlo.exists():
                shutil.move(zrodlo, cel / nazwa_celu)
        plik.sciezka_meta.unlink(missing_ok=True)

        plik.plik, plik.katalog, plik.sprawa = nowa_sciezka.name, cel, sprawa
        plik._zapisz_meta()
        return plik

    def usun(self, plik: ZapisanyPlik) -> None:
        for sciezka in (plik.sciezka, plik.sciezka_tekstu, plik.sciezka_meta):
            sciezka.unlink(missing_ok=True)

    @staticmethod
    def _wczytaj_katalog(katalog: Path) -> list[ZapisanyPlik]:
        if not katalog.exists():
            return []
        pliki = [ZapisanyPlik._wczytaj(m) for m in katalog.glob('*' + ROZSZERZENIE_META)]
        return sorted(pliki, key=lambda p: (p.dodano, p.plik))


def _bezpieczny_nr(sprawa: str) -> str:
    """Numer sprawy jako nazwa katalogu (np. „UDIP/1/2026” -> „UDIP_1_2026”)."""
    return re.sub(r'[^\w.\-]+', '_', sprawa).strip('._') or 'bez_numeru'


def _unikalna_sciezka(katalog: Path, nazwa: str) -> Path:
    sciezka = katalog / nazwa
    licznik = 2
    while sciezka.exists():
        sciezka = katalog / f'{Path(nazwa).stem}_{licznik}{Path(nazwa).suffix}'
        licznik += 1
    return sciezka
