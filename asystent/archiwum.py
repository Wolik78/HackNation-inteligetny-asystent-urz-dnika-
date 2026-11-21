"""Archiwum: wyszukiwanie podobnych spraw (Z5, I3, test jury J1).

Szukamy w:
- archiwalnych odpowiedziach z Bazy wiedzy (rodzaj „Archiwalna odpowiedź”),
- wnioskach z bieżącego rejestru z ostatnich 12 miesięcy (I3).

Trafność łączy dwie miary:
- słowa – wspólne rdzenie słów ważone rzadkością (TF-IDF; `program2.rdzenie` – ta sama normalizacja polskich
  słów co w doborze wydziałów). Działa zawsze, także bez LM Studio, i to ona niesie wynik: zmierzone na archiwum
  testowym trafia we właściwą sprawę także tam, gdzie model embeddingów się myli,
- znaczenie – podobieństwo wektorów (embeddingi z LM Studio, model `UDIP_EMBED_MODEL`) – łapie synonimy.
  Wbudowany w LM Studio nomic-embed słabo zna polski, więc dostaje małą wagę; model wielojęzyczny
  (np. bge-m3, multilingual-e5) – większą.
Wektory dokumentów są zapamiętywane w `indeks_archiwum.json` (po skrócie treści), więc liczy się je raz.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from . import rejestr
from .ai.bielik_service import BielikService, BladAI
from .ai.wydzialy import program2
from .konfiguracja import EMBED_MODEL, KATALOG_DANYCH
from .pliki import Kategoria, MagazynPlikow, ZapisanyPlik

log = logging.getLogger(__name__)

RODZAJ_ARCHIWUM = 'archiwum'
RODZAJ_WNIOSEK = 'wniosek'
OKRES_REJESTRU = timedelta(days=365)   # podobne wnioski z bieżącego rejestru – z ostatniego roku (I3)
ZNAKOW_DO_OSADZENIA = 1500             # początek dokumentu (temat, treść) – mieści się w oknie modelu embeddingów
LEX_PELNE = 0.40                       # podobieństwo słów (cosinus TF-IDF), od którego sprawa jest „w pełni” zgodna
SEM_PELNE = 0.10                       # o tyle ponad medianę podobieństw w archiwum – pełna zgodność znaczenia
PROG_WZORU = 40                        # najlepsza archiwalna odpowiedź od tylu % jest proponowana jako wzór pisma
SUFIT_ZA_WSPOLNE_SLOWA = {0: 0.3, 1: 0.6, 2: 0.8}   # najwyższy wynik przy tylu wspólnych słowach
PROG_POKAZANIA = 15                   # słabsze dopasowania nie są pokazywane (to już przypadkowe wspólne słowa)
CZESTE_SLOWO = 0.3                     # słowa z ponad 30% dokumentów („ustawy”, „art.”) nie są „wspólnym tematem”
NAZWA_INDEKSU = 'indeks_archiwum.json'
MODELE_WIELOJEZYCZNE = ('bge-m3', 'e5', 'multilingual', 'mmlw', 'gte')


def waga_znaczenia(model: str) -> float:
    """Udział podobieństwa znaczeniowego w wyniku – zależnie od tego, jak dobrze model zna polski."""
    return 0.5 if any(m in model.lower() for m in MODELE_WIELOJEZYCZNE) else 0.25


def _prefiksy(model: str) -> tuple[str, str]:
    """Prefiksy (pytanie, dokument), których wymagają niektóre modele embeddingów."""
    nazwa = model.lower()
    if 'nomic' in nazwa:
        return 'search_query: ', 'search_document: '
    if 'e5' in nazwa:
        return 'query: ', 'passage: '
    return '', ''


# --- dokumenty ---------------------------------------------------------------------------

@dataclass
class Dokument:
    klucz: str                         # 'archiwum:<plik>' albo 'wniosek:<id>'
    rodzaj: str
    tytul: str
    nr: str
    data: date | None
    tekst: str
    plik: ZapisanyPlik | None = None
    wniosek_id: int | None = None

    @property
    def opis_rodzaju(self) -> str:
        return 'Archiwalna odpowiedź' if self.rodzaj == RODZAJ_ARCHIWUM else 'Wniosek z rejestru'


@dataclass
class Trafienie:
    dokument: Dokument
    procent: int
    wspolne_slowa: list[str] = field(default_factory=list)
    fragment: str = ''


@dataclass
class WynikWyszukiwania:
    trafienia: list[Trafienie] = field(default_factory=list)
    tryb: str = 'slowa'                # 'hybryda' – słowa i znaczenie, 'slowa' – tylko słowa
    komunikat: str = ''
    liczba_dokumentow: int = 0

    @property
    def najlepszy_wzor(self) -> Trafienie | None:
        """Archiwalna odpowiedź, którą warto od razu podpowiedzieć jako wzór pisma."""
        return next((t for t in self.trafienia
                     if t.dokument.rodzaj == RODZAJ_ARCHIWUM and t.procent >= PROG_WZORU), None)


_NR = re.compile(r'\bUDIP[./]\d+[./]\d{4}\b', re.IGNORECASE)
_DATA = re.compile(r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b')
_DOTYCZY = re.compile(r'^\s*(?:dotyczy|dot\.)\s*:?\s*(.+)$', re.IGNORECASE | re.MULTILINE)


def opis_dokumentu(tekst: str, nazwa_pliku: str) -> tuple[str, str, date | None]:
    """(temat, numer sprawy, data) wyciągnięte z treści archiwalnej odpowiedzi; brakujące – z nazwy pliku."""
    rdzen = Path(nazwa_pliku).stem
    nr = (_NR.search(tekst) or _NR.search(rdzen.replace('_', ' ')))
    data = None
    if m := _DATA.search(tekst):
        try:
            data = date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            data = None
    if m := _DOTYCZY.search(tekst):
        # „wniosku z dnia 26.02.2025 r. o udostępnienie informacji publicznej w sprawie X” -> „W sprawie X”
        temat = re.sub(r'^wniosk\w*( z dnia [\d.]+ ?r\.?)?\s*', '', m[1].strip(), flags=re.IGNORECASE)
        temat = re.sub(r'^o udostępnienie informacji publicznej\s+(?=w sprawie|dotycz)', '', temat,
                       flags=re.IGNORECASE).rstrip('.')
    else:
        temat = re.sub(r'^UDIP[._]\d+[._]\d{4}_?', '', rdzen).replace('_', ' ').strip()
    temat = temat[:1].upper() + temat[1:] if temat else rdzen
    return temat, nr[0] if nr else '', data


_SEDNO = re.compile(r'\b(?:informuję|informujemy|przekazuję|przekazujemy)\b[^.:]*?(?:,? że|:)\s*', re.IGNORECASE)


def _fragment(tekst: str) -> str:
    """Krótki wycinek treści do podglądu: samo sedno odpowiedzi, bez formułek („na podstawie art. 2…”)."""
    if m := _SEDNO.search(tekst):
        start = m.end()
    elif m := _DOTYCZY.search(tekst):
        start = m.end()
    else:
        start = 0
    tresc = ' '.join(tekst[start:].split())
    tresc = re.sub(r'^(Szanown\w+ \w+,?\s*)', '', tresc)
    return tresc[:220] + ('…' if len(tresc) > 220 else '')


# --- słowa ---------------------------------------------------------------------------------

# Rdzenie słów z formułek każdego pisma UDIP („na podstawie art. 2 ust. 1 ustawy…”, „proszę przesłać na adres
# e-mail”, „Z poważaniem, z up. Prezydenta”) – nic nie mówią o temacie sprawy, a potrafią zmylić porównanie.
FORMULKI = frozenset({'adres', 'mail', 'email', 'przes', 'odpow', 'podst', 'art', 'ust', 'ustaw', 'udost', 'uprze',
                      'infor', 'powaz', 'szano', 'panst', 'prezy', 'podpi', 'zanon', 'brutt', 'zwiaz', 'zgodn'})


def _rdzenie(tekst: str) -> Counter:
    return Counter(r for r in program2.rdzenie(tekst) if r not in FORMULKI)


def _slowa_dokumentu(tekst: str) -> dict[str, str]:
    """{rdzeń: pierwsze słowo z tym rdzeniem w oryginalnej postaci} – żeby pokazać „promocję”, a nie „promo”."""
    slowa = {}
    for slowo in re.findall(r'[^\W\d_]{3,}', tekst):
        mala = program2.bez_ogonkow(slowo)
        if mala in program2.STOP:
            continue
        slowa.setdefault(program2.rdzen(mala), slowo.lower())
    return slowa


def _tfidf(licznik: Counter, idf: dict[str, float]) -> dict[str, float]:
    wektor = {r: (1 + math.log(n)) * idf[r] for r, n in licznik.items() if r in idf}
    norma = math.sqrt(sum(x * x for x in wektor.values())) or 1.0
    return {r: x / norma for r, x in wektor.items()}


# --- wyszukiwarka ----------------------------------------------------------------------------

class Archiwum:
    def __init__(self, magazyn: MagazynPlikow, bielik: BielikService, *,
                 katalog_indeksu: Path = KATALOG_DANYCH, model: str = EMBED_MODEL) -> None:
        self.magazyn = magazyn
        self.bielik = bielik
        self.model = model
        self.sciezka_indeksu = Path(katalog_indeksu) / NAZWA_INDEKSU
        self._indeks: dict[str, list[float]] | None = None
        self._blokada = asyncio.Lock()

    # --- dokumenty

    def dokumenty(self, *, pomin_wniosek: int | None = None, dzis: date | None = None) -> list[Dokument]:
        """Archiwalne odpowiedzi z Bazy wiedzy i wnioski z rejestru z ostatniego roku (bez bieżącego)."""
        dokumenty = []
        for plik in self.magazyn.lista(Kategoria.ARCHIWUM):
            tekst = plik.tekst()
            if not tekst.strip():
                continue
            temat, nr, data = opis_dokumentu(tekst, plik.nazwa_oryginalna)
            dokumenty.append(Dokument(f'archiwum:{plik.plik}', RODZAJ_ARCHIWUM, temat, nr,
                                      data or plik.data_dodania.date(), tekst, plik=plik))
        od = (dzis or date.today()) - OKRES_REJESTRU
        for w in rejestr.wszystkie():
            if w.id == pomin_wniosek or w.data_wplywu < od:
                continue
            pliki = self.magazyn.lista(Kategoria.WNIOSEK, sprawa=w.nr)
            tekst = '\n'.join([w.temat, *(p.tekst() for p in pliki)])
            dokumenty.append(Dokument(f'wniosek:{w.id}', RODZAJ_WNIOSEK, w.temat, w.nr, w.data_wplywu, tekst,
                                      wniosek_id=w.id))
        return dokumenty

    # --- wyszukiwanie

    async def szukaj(self, zapytanie: str, *, limit: int = 5, pomin_wniosek: int | None = None,
                     uzyj_ai: bool = True) -> WynikWyszukiwania:
        """Najbardziej podobne sprawy do tekstu wniosku (albo zapytania wpisanego w wyszukiwarkę)."""
        dokumenty = await asyncio.to_thread(self.dokumenty, pomin_wniosek=pomin_wniosek)
        if not dokumenty or not zapytanie.strip():
            return WynikWyszukiwania(liczba_dokumentow=len(dokumenty))

        slowa, df, ile_wspolnych = self._podobienstwo_slow(zapytanie, dokumenty)
        znaczenie, komunikat = None, ''
        if uzyj_ai:
            try:
                znaczenie = await self._podobienstwo_znaczenia(zapytanie, dokumenty)
            except BladAI as blad:
                komunikat = f'Wyszukiwanie tylko po słowach – model embeddingów niedostępny ({blad})'
        wynik = np.clip(slowa / LEX_PELNE, 0, 1)
        if znaczenie is not None:
            mediana = float(np.median(znaczenie)) if len(znaczenie) >= 4 else 1.0  # mało dokumentów – bez znaczenia
            waga = waga_znaczenia(self.model)
            wynik = (1 - waga) * wynik + waga * np.clip((znaczenie - mediana) / SEM_PELNE, 0, 1)
        # pewność rośnie z liczbą wspólnych słów: krótki temat z rejestru z jednym wspólnym słowem to nie „100%”
        wynik = np.minimum(wynik, [SUFIT_ZA_WSPOLNE_SLOWA.get(n, 1.0) for n in ile_wspolnych])

        # wspólne słowa „o temacie”: bez słów z ponad połowy dokumentów (ustawa, art., udostępnienie), rzadkie najpierw
        tematyczne = {r for r in _rdzenie(zapytanie) if df.get(r, 0) <= CZESTE_SLOWO * len(dokumenty)}
        trafienia = []
        for i in np.argsort(-wynik)[:limit]:
            procent = int(round(float(wynik[i]) * 100))
            if procent < PROG_POKAZANIA:
                break
            dokument = dokumenty[i]
            oryginalne = _slowa_dokumentu(dokument.tekst)
            wspolne = sorted((r for r in _rdzenie(dokument.tekst) if r in tematyczne and r in oryginalne),
                             key=lambda r: df[r])
            trafienia.append(Trafienie(dokument, procent, [oryginalne[r] for r in wspolne][:6],
                                       _fragment(dokument.tekst)))
        return WynikWyszukiwania(trafienia, 'hybryda' if znaczenie is not None else 'slowa', komunikat, len(dokumenty))

    @staticmethod
    def _podobienstwo_slow(zapytanie: str, dokumenty: list[Dokument]) -> tuple[np.ndarray, Counter, list[int]]:
        """(podobieństwo słów każdego dokumentu do zapytania, w ilu dokumentach występuje każdy rdzeń,
        ile różnych słów zapytania ma każdy dokument)."""
        liczniki = [_rdzenie(d.tekst) for d in dokumenty]
        df = Counter(r for licznik in liczniki for r in licznik)
        n = len(dokumenty)
        idf = {r: math.log((n + 1) / (k + 0.5)) for r, k in df.items()}
        # słowa zapytania nieznane w archiwum (nazwiska, adresy) nie zaniżają wyniku – nic o nim nie mówią
        pytanie = _tfidf(_rdzenie(zapytanie), idf)
        podobienstwo = np.array([sum(w * dok.get(r, 0.0) for r, w in pytanie.items())
                                 for dok in (_tfidf(licznik, idf) for licznik in liczniki)])
        return podobienstwo, df, [len(pytanie.keys() & licznik.keys()) for licznik in liczniki]

    async def _podobienstwo_znaczenia(self, zapytanie: str, dokumenty: list[Dokument]) -> np.ndarray:
        prefiks_pytania, _ = _prefiksy(self.model)
        wektory_dokumentow = await self._wektory_dokumentow(dokumenty)
        pytanie = np.array((await self.bielik.osadz([prefiks_pytania + zapytanie[:ZNAKOW_DO_OSADZENIA]],
                                                    self.model))[0])
        pytanie /= np.linalg.norm(pytanie) or 1.0
        return wektory_dokumentow @ pytanie

    # --- indeks wektorów

    async def zaindeksuj(self) -> int:
        """Liczy brakujące wektory archiwum (np. po wgraniu dokumentów do Bazy wiedzy). Zwraca ich liczbę."""
        dokumenty = await asyncio.to_thread(self.dokumenty)
        przed = len(self._wczytaj_indeks())
        await self._wektory_dokumentow(dokumenty)
        return len(self._wczytaj_indeks()) - przed

    async def _wektory_dokumentow(self, dokumenty: list[Dokument]) -> np.ndarray:
        _, prefiks = _prefiksy(self.model)
        teksty = [prefiks + d.tekst[:ZNAKOW_DO_OSADZENIA] for d in dokumenty]
        klucze = [hashlib.sha256(f'{self.model}\n{t}'.encode()).hexdigest() for t in teksty]
        async with self._blokada:  # dwa okna naraz nie liczą tych samych wektorów
            indeks = self._wczytaj_indeks()
            brakujace = [(k, t) for k, t in dict(zip(klucze, teksty)).items() if k not in indeks]
            if brakujace:
                nowe = await self.bielik.osadz([t for _, t in brakujace], self.model)
                indeks.update({k: [round(x, 6) for x in w] for (k, _), w in zip(brakujace, nowe)})
                self._zapisz_indeks(indeks)
        macierz = np.array([indeks[k] for k in klucze], dtype=float)
        return macierz / np.clip(np.linalg.norm(macierz, axis=1, keepdims=True), 1e-12, None)

    def _wczytaj_indeks(self) -> dict[str, list[float]]:
        if self._indeks is None:
            try:
                dane = json.loads(self.sciezka_indeksu.read_text('utf-8'))
                self._indeks = dict(dane.get('wektory', {}))
            except FileNotFoundError:
                self._indeks = {}
            except (ValueError, OSError, AttributeError):
                log.warning('Uszkodzony indeks archiwum %s – liczę wektory od nowa', self.sciezka_indeksu)
                self._indeks = {}
        return self._indeks

    def _zapisz_indeks(self, indeks: dict[str, list[float]]) -> None:
        self.sciezka_indeksu.parent.mkdir(parents=True, exist_ok=True)
        tymczasowy = self.sciezka_indeksu.with_suffix('.tmp')
        tymczasowy.write_text(json.dumps({'model': self.model, 'zapisano': datetime.now().isoformat(timespec='seconds'),
                                          'wektory': indeks}), 'utf-8')
        os.replace(tymczasowy, self.sciezka_indeksu)
