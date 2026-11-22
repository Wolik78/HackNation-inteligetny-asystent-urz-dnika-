"""Urzęduś – czat asystenta urzędnika, ograniczony do obsługi wniosków UDIP.

Przepływ jednej wiadomości:
1. Strażnik wejścia – za długie wiadomości, prośby o kod lub rozrywkę i próby obejścia zasad dostają
   stałą odmowę, bez pytania modelu.
2. Rozpoznanie intencji – najpierw słowa kluczowe (szybko i pewnie), a gdy nic nie pasuje, Bielik wybiera
   JEDNĄ intencję z zamkniętej listy. Model nie może „wymyślić” nowej czynności.
3. Wykonanie – każda intencja ma własny, ograniczony prompt i ściśle określone dane wejściowe.
4. Strażnik wyjścia – odpowiedź zawierająca kod albo znacznik POZA_TEMATEM jest przerywana i zastępowana odmową.

Urzęduś niczego nie zmienia ani nie wysyła sam – zmiany w sprawie GUI wykonuje dopiero po kliknięciu urzędnika.
"""

import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

from .. import rejestr
from ..anonimizacja import wykryj_wzorce
from ..kontrola import sprawdz_pismo
from ..rejestr import Wniosek
from . import prompty_czatu as prompty
from .bielik_service import BielikService, BladAI, wyciagnij_json
from .podrecznik import CALY_PODRECZNIK, znajdz_sekcje
from .tekst import normalizuj as _normalizuj
from .wydzialy import WynikDoboru, dobierz_async

MAKS_DLUGOSC_WIADOMOSCI = 1000
MAX_TOKENOW_ODPOWIEDZI = 500
MAX_TOKENOW_PISMA = 600


class Intencja(StrEnum):
    STRESZCZENIE = 'streszczenie'
    PYTANIE_O_SPRAWE = 'pytanie_o_sprawe'
    WYDZIALY = 'wydzialy'
    PROSBA_DO_WYDZIALU = 'prosba_do_wydzialu'
    ZAWIADOMIENIE = 'zawiadomienie_o_przedluzeniu'
    WEZWANIE = 'prosba_o_doprecyzowanie'
    PROJEKT = 'projekt_odpowiedzi'
    KONTROLA = 'kontrola_pisma'
    DANE_OSOBOWE = 'dane_osobowe'
    TERMINY = 'terminy'
    PRZEPISY = 'pytanie_o_przepisy'
    POMOC = 'pomoc_w_aplikacji'
    O_SOBIE = 'o_urzedusiu'
    ROZMOWA = 'rozmowa'
    POZA_TEMATEM = 'poza_tematem'


OPISY_INTENCJI = {
    Intencja.STRESZCZENIE: 'streszczenie wniosku – czego żąda wnioskodawca',
    Intencja.PYTANIE_O_SPRAWE: 'pytanie o treść dokumentów otwartej sprawy (wniosek, odpowiedzi wydziałów, projekt)',
    Intencja.WYDZIALY: 'wskazanie wydziałów urzędu, które mają potrzebne informacje',
    Intencja.PROSBA_DO_WYDZIALU: 'napisanie prośby do wydziału o przygotowanie informacji',
    Intencja.ZAWIADOMIENIE: 'napisanie zawiadomienia wnioskodawcy o przedłużeniu terminu',
    Intencja.WEZWANIE: 'napisanie prośby do wnioskodawcy o doprecyzowanie wniosku',
    Intencja.PROJEKT: 'przygotowanie projektu odpowiedzi na wniosek',
    Intencja.KONTROLA: 'sprawdzenie gotowego projektu pisma – czy liczby się zgadzają i czy odpowiada na wszystko',
    Intencja.DANE_OSOBOWE: 'wyszukanie danych osobowych do anonimizacji',
    Intencja.TERMINY: 'terminy – które wnioski trzeba załatwić dziś, jutro, które są po terminie',
    Intencja.PRZEPISY: 'pytanie o przepisy i procedurę udostępniania informacji publicznej',
    Intencja.POMOC: 'pytanie o tę aplikację – do czego służy ekran lub funkcja (np. Archiwum, Baza wiedzy), '
                    'jak coś w niej zrobić',
    Intencja.O_SOBIE: 'pytanie o samego asystenta – kim jest, co potrafi, jaki ma zakres obowiązków',
    Intencja.ROZMOWA: 'powitanie, podziękowanie, krótka grzecznościowa wiadomość',
    Intencja.POZA_TEMATEM: 'wszystko, co nie dotyczy pracy z wnioskami UDIP ani tej aplikacji',
}

WYMAGA_SPRAWY = {
    Intencja.STRESZCZENIE, Intencja.PYTANIE_O_SPRAWE, Intencja.WYDZIALY, Intencja.PROSBA_DO_WYDZIALU,
    Intencja.ZAWIADOMIENIE, Intencja.WEZWANIE, Intencja.PROJEKT, Intencja.DANE_OSOBOWE, Intencja.KONTROLA,
}
WYMAGA_TEKSTU_WNIOSKU = {Intencja.STRESZCZENIE, Intencja.WYDZIALY, Intencja.WEZWANIE}

POWITANIE = (
    'Cześć! Jestem Urzęduś, Twój asystent AI. Mogę pomóc w:\n'
    '• streszczeniu wniosku i odpowiedziach na pytania o dokumenty sprawy,\n'
    '• wskazaniu wydziałów, które mają potrzebne informacje,\n'
    '• napisaniu prośby do wydziału, zawiadomienia o przedłużeniu terminu albo prośby o doprecyzowanie wniosku,\n'
    '• przygotowaniu projektu odpowiedzi i sprawdzeniu go – czy liczby się zgadzają i czy odpowiada na wszystko,\n'
    '• wyszukaniu danych osobowych do anonimizacji,\n'
    '• sprawdzeniu terminów – co trzeba załatwić dziś i jutro,\n'
    '• wyjaśnieniu przepisów o dostępie do informacji publicznej,\n'
    '• podpowiedziach, jak korzystać z tej aplikacji.\n\n'
    'Zajmuję się wyłącznie wnioskami o dostęp do informacji publicznej i pracą w tej aplikacji. Niczego nie wysyłam '
    'ani nie zmieniam sam – każdą zmianę zatwierdzasz Ty.'
)

O_SOBIE = (
    'Jestem Urzęduś – asystent AI wbudowany w aplikację Asystent UDIP Urzędu Miasta Bydgoszczy. '
    'Mój zakres obowiązków:\n'
    '• praca na otwartej sprawie – streszczam wniosek, odpowiadam na pytania o jej dokumenty, proponuję wydziały, '
    'piszę prośby do wydziałów, zawiadomienia o przedłużeniu terminu, prośby o doprecyzowanie i projekt '
    'odpowiedzi, sprawdzam gotowe pismo, szukam danych osobowych do anonimizacji,\n'
    '• pilnowanie terminów – powiem, co trzeba załatwić dziś i jutro,\n'
    '• wyjaśnianie przepisów ustawy o dostępie do informacji publicznej,\n'
    '• pomoc w obsłudze aplikacji – np. do czego służy Archiwum albo jak wyeksportować pismo.\n\n'
    'Działam na modelu Bielik uruchomionym lokalnie, więc żaden dokument nie opuszcza tego komputera. '
    'Niczego nie wysyłam ani nie zmieniam sam – ostateczna decyzja zawsze należy do Ciebie. '
    'Nie zajmuję się tematami spoza pracy z wnioskami, np. programowaniem.'
)
POWITANIE_KROTKIE = ('Cześć! W czym mogę pomóc? Mogę np. streścić wniosek, sprawdzić terminy albo wyjaśnić, '
                     'jak działa aplikacja.')
PODZIEKOWANIE = 'Proszę bardzo! Gdybyś czegoś potrzebował przy wnioskach, jestem tutaj.'

ODMOWA = (
    'Tym się nie zajmuję – pomagam wyłącznie w obsłudze wniosków o dostęp do informacji publicznej '
    'i w pracy z tą aplikacją. Mogę na przykład streścić wniosek, wskazać wydziały, napisać projekt odpowiedzi, '
    'sprawdzić terminy albo wyjaśnić, do czego służy dany ekran.'
)
NIE_WIEM_O_APLIKACJI = (
    'Nie jestem pewien, o którą część aplikacji pytasz. Mogę opowiedzieć o ekranach: Wnioski, Nowy wniosek, '
    'Archiwum, Baza wiedzy, Ustawienia, a także o krokach sprawy – np. Projekt odpowiedzi, Anonimizacja, Eksport.'
)
BRAK_W_DOKUMENTACH = ('W dokumentach tej sprawy nie znalazłem odpowiedzi. '
                      'Odpowiadam tylko na podstawie dokumentów sprawy.')
BRAK_PODSTAWY_PRAWNEJ = (
    'Na to pytanie nie odpowiem – o przepisach mówię tylko wtedy, gdy mogę wskazać konkretny artykuł ustawy '
    'o dostępie do informacji publicznej. Zapytaj inaczej albo sprawdź w ustawie.'
)
ZA_DLUGA = f'Wiadomość jest za długa (limit {MAKS_DLUGOSC_WIADOMOSCI} znaków). Napisz krócej, o co chodzi.'
BRAK_SPRAWY = 'To dotyczy konkretnej sprawy. Otwórz wniosek z listy „Wnioski”, a zajmę się jego dokumentami.'
BRAK_WNIOSKU = 'W tej sprawie nie ma jeszcze pliku wniosku – wgraj go w kroku „Wniosek”.'


class OdpowiedzPozaTematem(Exception):
    """Model zaczął odpowiadać poza zakresem (kod, znacznik POZA_TEMATEM) – odpowiedź trzeba zastąpić odmową."""


@dataclass
class DaneSprawy:
    """To, co Urzęduś wie o otwartej sprawie (przekazuje GUI)."""
    nr: str
    temat: str
    data_wplywu: date
    termin: date
    tekst_wniosku: str = ''
    odpowiedzi_wydzialow: str = ''
    projekt: str = ''
    sugerowane_wydzialy: list[str] = field(default_factory=list)
    ukryte: set[str] = field(default_factory=set)   # dane osobowe zatwierdzone do ukrycia


@dataclass
class Wynik:
    intencja: Intencja
    tekst: str = ''                                  # gotowa odpowiedź (bez modelu)
    strumien: AsyncIterator[str] | None = None       # odpowiedź modelu na żywo
    wydzialy: WynikDoboru | None = None              # propozycja wydziałów do zapisania w sprawie
    dane_osobowe: list[str] = field(default_factory=list)
    zrodlo_danych_osobowych: str = ''                # 'projekt' albo 'wniosek'
    terminy: list[Wniosek] = field(default_factory=list)


# --- strażnicy -------------------------------------------------------------------------

_POZA_TEMATEM = [re.compile(w) for w in (
    r'\b(python\w*|javascript|typescript|java|c\+\+|c#|php|html|css|sql|bash|powershell|kotlin|rust|golang|matlab)\b',
    r'\bw (jezyku )?c\b',
    # „kod” bez „kodeksu”, „gra” bez „grantów” – urzędowe słowa nie mogą dawać fałszywej odmowy
    r'\b(napisz|stworz|zrob|zaprogramuj|wygeneruj|podaj|uloz|opowiedz|wymysl|powiedz)\b.{0,40}'
    r'\b(kod(u|em|zie|y)?\b|skrypt\w*|'
    r'kalkulator\w*|algorytm\w*|gr[eya]\b|wiersz\w*|piosenk\w*|opowiadani\w*|wypracowani\w*|dowcip\w*|'
    r'zart\w*|bajk\w*)',
    r'\b(zignoruj|pomin|zapomnij|olej)\b.{0,40}\b(instrukcj\w*|zasad\w*|polecen\w*|regul\w*|ograniczen\w*)',
    r'\b(ignore|disregard)\b.{0,40}\b(instructions|rules)\b',
    r'\b(jailbreak|prompt injection|system prompt)\b',
    r'\b(udawaj|odegraj|wciel sie)\b',
    r'\bprzepis\w* (kulinarn\w*|na)\b',  # „przepis na pierogi” – nie przepis prawny
)]

_CZASOWNIK_PISANIA = r'\b(napisz|przygotuj|wygeneruj|stworz|zredaguj|sporzadz|popros\w*)\b.{0,40}'

# Pytanie o aplikację = zwrot „do czego służy / jak zrobić / gdzie jest” + coś z aplikacji (w dowolnej kolejności).
_JAK_DO_CZEGO = (
    r'(do czego (sluz\w*|jest|sa|uzywa\w*)|co robi\w*|co to (jest|za)|czym (jest|sa)|po co\b|'
    r'co (o)?znacza\w*|na czym polega\w*|(o)?powiedz( mi)?( cos)? o\b|co (to )?za\b|'
    r'jak (\w+ )?(moge|mam|sie|dziala\w*|uzyw\w*|korzyst\w*|wgra\w*|doda\w*|zmieni\w*|zapisa\w*|otworzy\w*|'
    r'wyeksportowa\w*|eksportowa\w*|uruchomi\w*|zrobi\w*|napisa\w*|zanonimizowa\w*|wygenerowa\w*|usuna\w*|'
    r'znalez\w*)|gdzie (\w+ )?(jest|sa|znajde|moge|mam|wgra\w*|doda\w*))'
)
_ELEMENT_APLIKACJI = (
    r'(archiwum|baz\w* wiedzy|ustawieni\w*|kalendarz\w*|list\w* wnioskow|nowy wniosek|nowego wniosku|zakladk\w*|'
    r'ekran\w*|menu|przycisk\w*|krok\w*|anonimizacj\w*|zanonimizowa\w*|eksport\w*|wyeksportowa\w*|aplikacj\w*|'
    r'program\w*|narzedz\w*|system\w*|bielik\w*|plik\w*|wgra\w*|status\w*|tabel\w*|kafelk\w*|kolor\w*|'
    r'projekt\w*|pism\w*|word\w*|'
    r'docx|odpowiedzi wydzial\w*|podobne sprawy)'
)
_JAK_DO_CZEGO_RE = re.compile(r'\b' + _JAK_DO_CZEGO)
_ELEMENT_APLIKACJI_RE = re.compile(r'\b' + _ELEMENT_APLIKACJI)


def _pytanie_o_aplikacje(tekst: str) -> bool:
    return bool(_JAK_DO_CZEGO_RE.search(tekst) and _ELEMENT_APLIKACJI_RE.search(tekst))


_REGULY_INTENCJI = [  # kolejność ma znaczenie – bardziej szczegółowe najpierw
    (Intencja.O_SOBIE, r'\b(kim (ty )?jestes|co (po)?trafisz|co umiesz|w czym (\w+ ){0,2}pomo\w*|'
                       r'czym (\w+ ){0,2}zajmujesz|jak dzialasz|co (\w+ ){0,3}robisz|'
                       r'twoj\w* (zakres|obowiazk|zadan|mozliwos|funkcj|rol)|'
                       r'zakres\w* (twoich )?obowiazk\w*)'),
    (Intencja.POMOC, _pytanie_o_aplikacje),
    (Intencja.KONTROLA, r'\b(sprawdz\w*|zweryfikuj\w*|skontroluj\w*|przejrzyj|przeanalizuj)\b.{0,30}'
                        r'\b(pism\w*|projekt\w*|odpowiedz\w*)|'
                        r'\bczy (to )?(pismo|projekt)\b.{0,40}\b(poprawn\w*|kompletn\w*|odpowiada\w*|dobr\w*|ok)\b'),
    (Intencja.ZAWIADOMIENIE, r'\bzawiadomieni\w*\b|' + _CZASOWNIK_PISANIA + r'\b(przedluz\w*|wydluz\w*)'),
    (Intencja.WEZWANIE, r'\bwezwani\w*\b|' + _CZASOWNIK_PISANIA + r'\b(doprecyz\w*|uscisl\w*)'),
    (Intencja.PROSBA_DO_WYDZIALU, r'\b(prosb\w*|pism\w*|mail\w*|zapytani\w*|wiadomosc\w*)\s+(do|dla)\s+'
                                  r'(wydzial\w*|biur\w*|komork\w*)'),
    (Intencja.PROJEKT, r'\b(napisz|wygeneruj|przygotuj|stworz|zrob|utworz|zredaguj)\b.{0,30}'
                       r'\b(projekt\w*|odpowiedz\w*|pism\w*)'),
    (Intencja.DANE_OSOBOWE, r'(dane osobow|danych osobow|anonimiz|\brodo\b|\bpesel)'),
    (Intencja.PRZEPISY, r'\b(ustaw\w*|art\.?|artykul\w*|przepis\w*|udip|przetworzon\w*|odmow\w*|decyzj\w*|'
                        r'umorz\w*|oplat\w*)\b|\bile (dni|czasu)\b.{0,40}\b(odpowiedz\w*|udostepn\w*|urzad\w*)'),
    (Intencja.STRESZCZENIE, r'\b(strescz\w*|stresc\w*|podsumuj\w*|podsumowani\w*|o co chodzi|czego dotyczy)\b'),
    (Intencja.WYDZIALY, r'\b(zaproponuj|wskaz\w*|ktor\w*|jaki\w*|do kogo|gdzie)\b.{0,30}'
                        r'\b(wydzial\w*|komork\w*|biur\w*)'),
    (Intencja.TERMINY, r'\b(termin\w*|na dzis|na jutro|dzisiaj|zaleg\w*|po terminie|pilne\w*)\b'),
]
_REGULY_INTENCJI = [(intencja, wzorzec if callable(wzorzec) else re.compile(wzorzec).search)
                    for intencja, wzorzec in _REGULY_INTENCJI]

_KOD_W_ODPOWIEDZI = re.compile(
    r'```|#include\s*<|\bint\s+main\s*\(|\bdef\s+\w+\s*\(|\bpublic\s+static\b|\bfunction\s+\w+\s*\(|'
    r'\bconsole\.log\b|\bprintf\s*\(|\bscanf\s*\(|\bSystem\.out\b|<\s*script\b'
)


def jest_poza_tematem(wiadomosc: str) -> bool:
    tekst = _normalizuj(wiadomosc)
    return any(wzorzec.search(tekst) for wzorzec in _POZA_TEMATEM)


_ZDANIE_PYTAJACE = re.compile(r'^\W*(czy|jak|jaki\w*|kiedy|ile|dlaczego|po co|w jakim|na jakiej|co)\b')
_PISANIE_PISM = {Intencja.ZAWIADOMIENIE, Intencja.WEZWANIE, Intencja.PROSBA_DO_WYDZIALU, Intencja.PROJEKT}
_PODZIEKOWANIE = re.compile(r'\b(dzieki|dziekuje\w*|dziekowac|thx|thanks)\b')
_SLOWA_GRZECZNOSCIOWE = {
    'czesc', 'hej', 'hejka', 'siema', 'siemka', 'witam', 'witaj', 'dzien', 'dobry', 'wieczor', 'elo', 'yo',
    'dzieki', 'dziekuje', 'bardzo', 'wielkie', 'super', 'ok', 'okej', 'spoko', 'jasne', 'swietnie', 'thx',
    'thanks', 'urzedus', 'urzedusiu', 'pa', 'nara', 'dobranoc',
}


def _tylko_grzecznosc(tekst: str) -> bool:
    """„Cześć!”, „Dzięki, super” – tak; „Cześć, streść wniosek” – nie (to polecenie)."""
    slowa = re.findall(r'\w+', tekst)
    return bool(slowa) and all(s in _SLOWA_GRZECZNOSCIOWE for s in slowa)


def rozpoznaj_lokalnie(wiadomosc: str) -> Intencja | None:
    """Rozpoznanie po słowach kluczowych; None, gdy trzeba zapytać model.

    Zdanie pytające („Czy można przedłużyć termin?”) nigdy nie uruchamia pisania pisma.
    """
    if jest_poza_tematem(wiadomosc):
        return Intencja.POZA_TEMATEM
    tekst = _normalizuj(wiadomosc)
    if _tylko_grzecznosc(tekst):
        return Intencja.ROZMOWA
    pytanie = bool(_ZDANIE_PYTAJACE.match(tekst))
    return next((intencja for intencja, pasuje in _REGULY_INTENCJI
                 if pasuje(tekst) and not (pytanie and intencja in _PISANIE_PISM)), None)


# Słownictwo pracy z wnioskami – zawsze „w temacie”, nawet gdy nie pada dosłownie w dokumentach.
_SLOWNICTWO_URZEDOWE = (
    'wydzia', 'wnios', 'inform', 'odpowie', 'kwot', 'termin', 'spraw', 'urzed', 'dokument', 'poda', 'przekaz',
    'wskaz', 'zawier', 'brak', 'dotycz', 'dane', 'danych', 'udostep', 'publiczn', 'tresc', 'pism', 'biur',
    'projekt', 'zloz', 'wykonaw', 'umow', 'koszt', 'wydat',
)


def jest_oparta_na_dokumentach(odpowiedz: str, dokumenty: str, prog: float = 0.4) -> bool:
    """Czy odpowiedź używa słownictwa z dokumentów sprawy (rdzenie słów – odporne na odmianę).

    Odpowiedź „z głowy” (np. o stolicy Francji) nie ma pokrycia w dokumentach i zostaje odrzucona.
    Słowa z pytania celowo się nie liczą – inaczej odpowiedź na pytanie spoza tematu by przeszła.
    """
    if 'nie ma tej informacji' in odpowiedz.lower():
        return True
    rdzenie = {s[:5] for s in re.findall(r'\w{5,}', _normalizuj(dokumenty))}
    slowa = re.findall(r'\w{4,}', _normalizuj(odpowiedz))
    if not slowa:
        return True
    oparte = sum(s[:5] in rdzenie or s.startswith(_SLOWNICTWO_URZEDOWE) for s in slowa)
    return oparte / len(slowa) >= prog


def narusza_zakres(odpowiedz: str) -> bool:
    return prompty.ZNACZNIK_POZA_TEMATEM in odpowiedz[:80] or bool(_KOD_W_ODPOWIEDZI.search(odpowiedz))


async def pilnuj_zakresu(strumien: AsyncIterator[str]) -> AsyncIterator[str]:
    """Przepuszcza odpowiedź modelu, ale przerywa ją (OdpowiedzPozaTematem), gdy wyjdzie poza zakres.

    Początek odpowiedzi jest wstrzymywany, żeby znacznik POZA_TEMATEM nie pojawił się na ekranie.
    """
    bufor, wyslano = '', 0
    async with aclosing(strumien) as zrodlo:
        async for kawalek in zrodlo:
            bufor += kawalek
            if narusza_zakres(bufor):
                raise OdpowiedzPozaTematem
            if len(bufor) >= 30:
                yield bufor[wyslano:]
                wyslano = len(bufor)
    if narusza_zakres(bufor):
        raise OdpowiedzPozaTematem
    if wyslano < len(bufor):
        yield bufor[wyslano:]


# --- Urzęduś -----------------------------------------------------------------------------

class Urzedus:
    def __init__(self, bielik: BielikService,
                 dobor_wydzialow: Callable[[str], Awaitable[WynikDoboru]] = dobierz_async) -> None:
        self.bielik = bielik
        self.dobor_wydzialow = dobor_wydzialow  # moduł doboru wydziałów z BIP (asystent/ai/wydzialy.py)

    async def rozpoznaj(self, wiadomosc: str, ma_sprawe: bool) -> Intencja:
        if (intencja := rozpoznaj_lokalnie(wiadomosc)) is not None:
            return intencja
        try:
            odpowiedz = await self.bielik.zapytaj(prompty.router(wiadomosc, OPISY_INTENCJI), max_tokens=40)
            dane = wyciagnij_json(odpowiedz)
            # Bielik raz pisze "intencja", raz "intent" – bierzemy wartość niezależnie od nazwy klucza
            wartosc = dane.get('intencja') or dane.get('intent') or \
                next((v for v in dane.values() if isinstance(v, str)), '')
            return Intencja(str(wartosc).strip().lower())
        except (BladAI, ValueError):
            # Nie wiadomo, o co chodzi – odpowiadamy w trybie pytania, którego prompt i tak pilnuje zakresu.
            return Intencja.PYTANIE_O_SPRAWE if ma_sprawe else Intencja.PRZEPISY

    async def obsluz(self, wiadomosc: str, sprawa: DaneSprawy | None, historia: str = '',
                     intencja: Intencja | None = None) -> Wynik:
        """Obsługuje wiadomość albo – gdy podano `intencja` – szybką akcję z przycisku."""
        wiadomosc = wiadomosc.strip()
        if len(wiadomosc) > MAKS_DLUGOSC_WIADOMOSCI:
            return Wynik(Intencja.POZA_TEMATEM, tekst=ZA_DLUGA)
        if intencja is None:
            intencja = await self.rozpoznaj(wiadomosc, ma_sprawe=sprawa is not None)

        if intencja is Intencja.POZA_TEMATEM:
            return Wynik(intencja, tekst=ODMOWA)
        if intencja is Intencja.O_SOBIE:
            return Wynik(intencja, tekst=O_SOBIE)
        if intencja is Intencja.ROZMOWA:
            podziekowanie = _PODZIEKOWANIE.search(_normalizuj(wiadomosc))
            return Wynik(intencja, tekst=PODZIEKOWANIE if podziekowanie else POWITANIE_KROTKIE)
        if intencja is Intencja.POMOC:
            return self._pomoc(wiadomosc)
        if intencja is Intencja.TERMINY:
            return self._terminy()
        if intencja is Intencja.PRZEPISY or (sprawa is None and intencja is Intencja.PYTANIE_O_SPRAWE):
            # pytanie bez otwartej sprawy traktujemy jak pytanie o przepisy
            return Wynik(Intencja.PRZEPISY, strumien=self._przepisy(wiadomosc))
        if sprawa is None:
            return Wynik(intencja, tekst=BRAK_SPRAWY)
        if intencja in WYMAGA_TEKSTU_WNIOSKU and not sprawa.tekst_wniosku.strip():
            return Wynik(intencja, tekst=BRAK_WNIOSKU)

        match intencja:
            case Intencja.STRESZCZENIE:
                return Wynik(intencja, strumien=self._odpowiedz(prompty.streszczenie(sprawa.tekst_wniosku)))
            case Intencja.WYDZIALY:
                return await self._wydzialy(sprawa)
            case Intencja.DANE_OSOBOWE:
                return await self._dane_osobowe(sprawa)
            case Intencja.PROJEKT:
                return Wynik(intencja, strumien=self._projekt(sprawa))
            case Intencja.KONTROLA:
                if not sprawa.projekt.strip():
                    return Wynik(intencja, tekst='Nie ma jeszcze projektu odpowiedzi do sprawdzenia – '
                                                 'przygotuj go w kroku „Projekt odpowiedzi”.')
                return Wynik(intencja, strumien=self._kontrola(sprawa))
            case Intencja.PROSBA_DO_WYDZIALU:
                return Wynik(intencja, strumien=self._pismo(prompty.PROSBA_DO_WYDZIALU, sprawa))
            case Intencja.ZAWIADOMIENIE:
                return Wynik(intencja, strumien=self._pismo(prompty.ZAWIADOMIENIE_O_PRZEDLUZENIU, sprawa))
            case Intencja.WEZWANIE:
                return Wynik(intencja, strumien=self._pismo(prompty.WEZWANIE_DO_DOPRECYZOWANIA, sprawa))
            case _:
                return Wynik(Intencja.PYTANIE_O_SPRAWE, strumien=self._pytanie_o_sprawe(wiadomosc, sprawa, historia))

    # --- czynności ---

    def _odpowiedz(self, wiadomosci: list[dict], max_tokens: int = MAX_TOKENOW_ODPOWIEDZI) -> AsyncIterator[str]:
        return pilnuj_zakresu(self.bielik.strumieniuj(wiadomosci, max_tokens=max_tokens))

    def _pomoc(self, pytanie: str) -> Wynik:
        """Pytanie o aplikację: typowe – od razu z podręcznika, nietypowe – Bielik na podstawie podręcznika."""
        if sekcja := znajdz_sekcje(pytanie):
            return Wynik(Intencja.POMOC, tekst=sekcja.tekst)
        return Wynik(Intencja.POMOC, strumien=self._pomoc_modelu(pytanie))

    async def _pomoc_modelu(self, pytanie: str) -> AsyncIterator[str]:
        odpowiedz = ''.join([k async for k in self._odpowiedz(prompty.pomoc_aplikacja(pytanie, CALY_PODRECZNIK))])
        yield odpowiedz if jest_oparta_na_dokumentach(odpowiedz, CALY_PODRECZNIK) else NIE_WIEM_O_APLIKACJI

    async def _przepisy(self, pytanie: str) -> AsyncIterator[str]:
        """Odpowiedź o przepisach pokazujemy w całości dopiero po sprawdzeniu, że powołuje się na artykuł ustawy.

        Mały model potrafi zignorować zakaz i odpowiedzieć na pytanie spoza tematu – wtedy nie będzie
        w odpowiedzi podstawy prawnej i nic z niej nie trafi na ekran.
        """
        odpowiedz = ''.join([k async for k in self._odpowiedz(prompty.pytanie_ogolne(pytanie))])
        if re.search(r'\bart\.\s*\d', odpowiedz) or 'Nie mam pewności' in odpowiedz:
            yield odpowiedz
        else:
            yield BRAK_PODSTAWY_PRAWNEJ

    async def _pytanie_o_sprawe(self, pytanie: str, sprawa: DaneSprawy, historia: str) -> AsyncIterator[str]:
        """Odpowiedź pokazujemy dopiero, gdy jest oparta na dokumentach sprawy (krótka, więc czekamy na całość)."""
        dokumenty = await self._dokumenty(sprawa)
        odpowiedz = ''.join([k async for k in self._odpowiedz(prompty.pytanie_o_sprawe(pytanie, dokumenty, historia))])
        yield odpowiedz if jest_oparta_na_dokumentach(odpowiedz, dokumenty) else BRAK_W_DOKUMENTACH

    async def _kontrola(self, sprawa: DaneSprawy) -> AsyncIterator[str]:
        """Najpierw natychmiastowa kontrola bez AI, potem (dłużej) kompletność oceniana przez Bielika."""
        wynik = sprawdz_pismo(
            sprawa.projekt, [('wniosek', sprawa.tekst_wniosku)],
            do_pokrycia=[('odpowiedzi wydziałów', sprawa.odpowiedzi_wydzialow)], ukryte=sprawa.ukryte,
            dane_sprawy=[sprawa.nr, f'{sprawa.data_wplywu:%d.%m.%Y}', f'{sprawa.termin:%d.%m.%Y}',
                         f'{date.today():%d.%m.%Y}'])
        linie = [f'Wartości potwierdzone w źródłach: {len(wynik.potwierdzone)}.']
        if wynik.problemy:
            linie.append('Do poprawy:' if wynik.bledy else 'Uwagi:')
            linie += [f'• {p.opis}' for p in wynik.problemy]
        else:
            linie.append('Liczby, daty i forma pisma są w porządku.')
        yield '\n'.join(linie)

        if not sprawa.tekst_wniosku.strip():
            yield '\n\nKompletności nie sprawdzę – w sprawie nie ma pliku wniosku.'
            return
        try:
            zadania = await self.bielik.sprawdz_kompletnosc(sprawa.tekst_wniosku, sprawa.projekt)
        except BladAI as blad:
            yield f'\n\nKompletności nie sprawdziłem: {blad}'
            return
        linie = [f'{"✓" if z.odpowiedziano else "✗"} {z.tresc}' + ('' if z.odpowiedziano else ' – brak odpowiedzi')
                 for z in zadania]
        yield '\n\nOdpowiedzi na żądania wniosku:\n' + '\n'.join(linie)

    def _projekt(self, sprawa: DaneSprawy) -> AsyncIterator[str]:
        return pilnuj_zakresu(self.bielik.generuj_odpowiedz(
            wniosek=sprawa.tekst_wniosku or f'Wniosek dotyczy: {sprawa.temat}.',
            informacje_wydzialow=sprawa.odpowiedzi_wydzialow or '(wydziały nie przekazały jeszcze informacji)'))

    def _pismo(self, rodzaj_i_instrukcja: tuple[str, str], sprawa: DaneSprawy) -> AsyncIterator[str]:
        rodzaj, instrukcja = rodzaj_i_instrukcja
        termin_wydzialu = max(sprawa.termin - timedelta(days=3), date.today())
        dane = (f'Numer sprawy: {sprawa.nr}\nTemat: {sprawa.temat}\n'
                f'Data wpływu wniosku: {sprawa.data_wplywu:%d.%m.%Y}\n'
                f'Termin odpowiedzi (14 dni): {sprawa.termin:%d.%m.%Y}\n'
                f'Termin dla wydziału: {termin_wydzialu:%d.%m.%Y}\n'
                f'Najpóźniejszy termin po przedłużeniu (2 miesiące): '
                f'{sprawa.data_wplywu + timedelta(days=60):%d.%m.%Y}\n'
                f'Sugerowane wydziały: {", ".join(sprawa.sugerowane_wydzialy) or "brak"}')
        tekst_wniosku = sprawa.tekst_wniosku or f'Wniosek dotyczy: {sprawa.temat}.'
        return self._odpowiedz(prompty.pismo(rodzaj, instrukcja, tekst_wniosku[:3000], dane),
                               max_tokens=MAX_TOKENOW_PISMA)

    async def _wydzialy(self, sprawa: DaneSprawy) -> Wynik:
        wynik = await self.dobor_wydzialow(sprawa.tekst_wniosku)
        if not wynik.propozycje:
            return Wynik(Intencja.WYDZIALY, tekst='Nie udało się wskazać wydziałów. '
                         + (wynik.komunikat or 'Wybierz je ręcznie w kroku „Wydziały”.'))
        linie = [f'• {p.etykieta}' + (f' – {p.uzasadnienie}' if p.uzasadnienie else '') for p in wynik.propozycje]
        tekst = 'Proponuję skierować prośbę do:\n' + '\n'.join(linie) + f'\n\n({wynik.opis_zrodla})'
        return Wynik(Intencja.WYDZIALY, tekst=tekst, wydzialy=wynik)

    async def _dane_osobowe(self, sprawa: DaneSprawy) -> Wynik:
        zrodlo, tekst = ('projekt', sprawa.projekt) if sprawa.projekt.strip() else ('wniosek', sprawa.tekst_wniosku)
        if not tekst.strip():
            return Wynik(Intencja.DANE_OSOBOWE, tekst='Nie ma jeszcze projektu odpowiedzi ani pliku wniosku do '
                                                      'sprawdzenia.')
        znalezione = list(wykryj_wzorce(tekst))
        for ciag in await self.bielik.wykryj_dane_osobowe(tekst):
            if ciag not in znalezione:
                znalezione.append(ciag)
        gdzie = 'projekcie odpowiedzi' if zrodlo == 'projekt' else 'treści wniosku'
        if not znalezione:
            return Wynik(Intencja.DANE_OSOBOWE, tekst=f'Nie znalazłem danych osobowych w {gdzie}.',
                         zrodlo_danych_osobowych=zrodlo)
        tekst_wyniku = f'W {gdzie} znalazłem dane do ukrycia:\n' + '\n'.join(f'• {c}' for c in znalezione)
        return Wynik(Intencja.DANE_OSOBOWE, tekst=tekst_wyniku, dane_osobowe=znalezione,
                     zrodlo_danych_osobowych=zrodlo)

    @staticmethod
    def _terminy() -> Wynik:
        pilne = [w for w in rejestr.wszystkie() if w.pilnosc in ('po_terminie', 'dzis', 'jutro', 'blisko')]
        pilne.sort(key=lambda w: w.dni_do_terminu)
        if not pilne:
            return Wynik(Intencja.TERMINY, tekst='Nie masz pilnych wniosków – żaden termin nie mija w ciągu 3 dni.')
        linie = [f'• {w.nr} – {w.temat} ({w.pozostalo}, termin {w.termin:%d.%m.%Y})' for w in pilne]
        return Wynik(Intencja.TERMINY, tekst='Pilne wnioski:\n' + '\n'.join(linie), terminy=pilne)

    async def _dokumenty(self, sprawa: DaneSprawy) -> str:
        limit = await self.bielik.dostepny_limit_znakow(MAX_TOKENOW_ODPOWIEDZI)
        czesci = [('WNIOSEK', sprawa.tekst_wniosku, 0.35), ('ODPOWIEDZI WYDZIAŁÓW', sprawa.odpowiedzi_wydzialow, 0.45),
                  ('PROJEKT ODPOWIEDZI', sprawa.projekt, 0.20)]
        naglowek = f'Sprawa {sprawa.nr}: {sprawa.temat}. Termin odpowiedzi: {sprawa.termin:%d.%m.%Y}.'
        return '\n\n'.join([naglowek] + [f'[{nazwa}]\n{tekst[:int(limit * udzial)]}'
                                         for nazwa, tekst, udzial in czesci if tekst.strip()])
