"""Klient lokalnego modelu Bielik (LM Studio, API zgodne z OpenAI).

Zapytania idą wyłącznie na lokalny serwer – dokumenty nie opuszczają komputera.
Wszystkie metody są asynchroniczne (httpx), więc interfejs nie zawiesza się podczas generowania.
Błędy (wyłączone LM Studio, przekroczony czas, zły format odpowiedzi) zgłaszane są jako BladAI
z komunikatem, który można pokazać urzędnikowi.
"""

import json
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx

from ..konfiguracja import LLM_LIMIT_ZNAKOW, LLM_MODEL, LLM_TEMPERATURA, LLM_URL
from . import prompty

log = logging.getLogger(__name__)

ZNAKOW_NA_TOKEN = 3.0          # zmierzone dla Bieliku: ~3,3 znaku polskiego tekstu na token (z zapasem)
REZERWA_NA_PROMPT = 400        # tokeny na instrukcje systemowe i formatowanie
MAX_TOKENOW_ANALIZY = 400
MAX_TOKENOW_DANYCH_OSOBOWYCH = 400
MAX_TOKENOW_PISMA = 700
MAX_TOKENOW_KOMPLETNOSCI = 500
CZAS_ODPOWIEDZI = 240.0        # s – mały model na GPU laptopa potrafi myśleć ponad minutę


class BladAI(Exception):
    """Błąd modelu z komunikatem do pokazania urzędnikowi."""


@dataclass
class AnalizaWniosku:
    skrocony_opis: str
    sugerowane_wydzialy: list[str] = field(default_factory=list)
    uzasadnienie_wydzialu: str = ''
    czy_wymaga_kwerendy: bool = False


@dataclass
class Zadanie:
    """Jedno żądanie z wniosku i to, czy projekt pisma na nie odpowiada."""
    tresc: str
    odpowiedziano: bool
    fragment: str = ''     # cytat z projektu potwierdzający odpowiedź (zweryfikowany)


@dataclass
class StatusModelu:
    dostepny: bool
    komunikat: str
    kontekst: int | None = None


class BielikService:
    def __init__(self, url: str = LLM_URL, model: str = LLM_MODEL, *, temperatura: float = LLM_TEMPERATURA,
                 limit_znakow: int = LLM_LIMIT_ZNAKOW, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.url = url.rstrip('/')
        self.model = model
        self.temperatura = temperatura
        self.limit_znakow = limit_znakow
        self._transport = transport  # w testach: httpx.MockTransport
        self._kontekst: int | None = None

    # --- publiczne API ------------------------------------------------------------

    async def status(self) -> StatusModelu:
        """Szybkie sprawdzenie, czy LM Studio działa i ma załadowany model."""
        try:
            async with self._klient(httpx.Timeout(3.0)) as klient:
                odpowiedz = await klient.get(f'{self.url}/models')
                odpowiedz.raise_for_status()
                modele = [m.get('id') for m in odpowiedz.json().get('data', [])]
        except (httpx.HTTPError, ValueError):
            return StatusModelu(False, f'LM Studio nie odpowiada ({self.url}). Uruchom serwer w LM Studio.')
        if self.model not in modele:
            return StatusModelu(False, f'W LM Studio nie ma modelu „{self.model}”.')
        kontekst = await self._pobierz_kontekst()
        opis = f'Bielik gotowy (okno kontekstu: {kontekst} tokenów)' if kontekst else 'Bielik gotowy'
        return StatusModelu(True, opis, kontekst)

    async def analizuj_wniosek(self, tekst: str, znane_wydzialy: list[str] | None = None) -> AnalizaWniosku:
        """Skrócony opis, sugerowane wydziały i ocena, czy potrzebna jest kwerenda."""
        limit = await self._limit_znakow(MAX_TOKENOW_ANALIZY)
        odpowiedz = await self._czat(prompty.analiza_wniosku(tekst[:limit], znane_wydzialy),
                                     max_tokens=MAX_TOKENOW_ANALIZY)
        dane = wyciagnij_json(odpowiedz)
        wydzialy = dane.get('sugerowane_wydzialy') or []
        if isinstance(wydzialy, str):
            wydzialy = [wydzialy]
        return AnalizaWniosku(
            skrocony_opis=str(dane.get('skrocony_opis') or '').strip(),
            sugerowane_wydzialy=[str(w).strip() for w in wydzialy if str(w).strip()][:5],
            uzasadnienie_wydzialu=str(dane.get('uzasadnienie_wydzialu') or '').strip(),
            czy_wymaga_kwerendy=_na_bool(dane.get('czy_wymaga_kwerendy')),
        )

    async def wykryj_dane_osobowe(self, tekst: str) -> list[str]:
        """Ciągi znaków z danymi osób prywatnych, które występują dosłownie w tekście.

        Długi tekst dzielimy na części, żeby sprawdzić go w całości mimo małego okna kontekstu.
        """
        limit = await self._limit_znakow(MAX_TOKENOW_DANYCH_OSOBOWYCH)
        znalezione: list[str] = []
        for czesc in podziel_tekst(tekst, limit):
            odpowiedz = await self._czat(prompty.dane_osobowe(czesc), max_tokens=MAX_TOKENOW_DANYCH_OSOBOWYCH)
            kandydaci = wyciagnij_json(odpowiedz).get('do_ukrycia') or []
            if isinstance(kandydaci, str):
                kandydaci = [kandydaci]
            for kandydat in kandydaci:
                # model podaje formę podstawową („Jan Kowalski”) albo poprawia zapis – szukamy tego,
                # co naprawdę jest w tekście („Janie Kowalski”), a zmyślenia odrzucamy
                for ciag in dopasuj_w_tekscie(str(kandydat).strip(), tekst):
                    if ciag not in znalezione:
                        znalezione.append(ciag)
        return znalezione

    async def sprawdz_kompletnosc(self, wniosek: str, projekt: str) -> list[Zadanie]:
        """Czy projekt odpowiada na wszystkie żądania z wniosku.

        Model bywa zbyt łaskawy (potrafi napisać „odpowiedziano”, nie wskazując gdzie), dlatego żądanie
        uznajemy za spełnione tylko wtedy, gdy model zacytuje fragment projektu i ten fragment naprawdę w nim jest.
        """
        limit = await self._limit_znakow(MAX_TOKENOW_KOMPLETNOSCI)
        odpowiedz = await self._czat(
            prompty.kompletnosc(wniosek[:int(limit * 0.45)], projekt[:int(limit * 0.55)]),
            max_tokens=MAX_TOKENOW_KOMPLETNOSCI)
        dane = wyciagnij_json(odpowiedz)
        zadania = dane.get('zadania') or dane.get('żądania') or next(
            (v for v in dane.values() if isinstance(v, list)), [])
        wynik = []
        for pozycja in zadania:
            if not isinstance(pozycja, dict):
                continue
            tresc = str(pozycja.get('zadanie') or pozycja.get('żądanie') or '').strip()
            if not tresc:
                continue
            fragment = str(pozycja.get('fragment') or '').strip()
            potwierdzone = _na_bool(pozycja.get('odpowiedziano')) and fragment_w_tekscie(fragment, projekt)
            wynik.append(Zadanie(tresc, potwierdzone, fragment if potwierdzone else ''))
        if not wynik:
            raise BladAI('Bielik nie wskazał żądań z wniosku. Spróbuj ponownie.')
        return wynik

    async def generuj_odpowiedz(self, *, wniosek: str, informacje_wydzialow: str,
                                wzor: str | None = None) -> AsyncIterator[str]:
        """Strumieniuje projekt pisma kawałek po kawałku (do wyświetlania na żywo)."""
        limit = await self._limit_znakow(MAX_TOKENOW_PISMA)
        wniosek, informacje_wydzialow, wzor = przytnij_do_budzetu(limit, wniosek, informacje_wydzialow, wzor)
        async for kawalek in self._strumien(prompty.projekt_odpowiedzi(wniosek, informacje_wydzialow, wzor),
                                            max_tokens=MAX_TOKENOW_PISMA):
            yield kawalek

    async def zapytaj(self, wiadomosci: list[dict], *, max_tokens: int) -> str:
        """Pojedyncza odpowiedź modelu (np. do klasyfikacji polecenia w czacie)."""
        return await self._czat(wiadomosci, max_tokens=max_tokens)

    async def strumieniuj(self, wiadomosci: list[dict], *, max_tokens: int) -> AsyncIterator[str]:
        """Odpowiedź modelu kawałek po kawałku (do wyświetlania na żywo)."""
        async for kawalek in self._strumien(wiadomosci, max_tokens=max_tokens):
            yield kawalek

    async def dostepny_limit_znakow(self, max_tokens_odpowiedzi: int) -> int:
        """Ile znaków tekstu można wysłać, żeby zmieścić się w oknie kontekstu modelu."""
        return await self._limit_znakow(max_tokens_odpowiedzi)

    # --- komunikacja z serwerem ---------------------------------------------------------

    def _klient(self, timeout: httpx.Timeout) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, transport=self._transport)

    @staticmethod
    def _timeout() -> httpx.Timeout:
        return httpx.Timeout(CZAS_ODPOWIEDZI, connect=3.0)

    def _payload(self, wiadomosci: list[dict], max_tokens: int, stream: bool) -> dict:
        return {'model': self.model, 'messages': wiadomosci, 'temperature': self.temperatura,
                'max_tokens': max_tokens, 'stream': stream}

    async def _czat(self, wiadomosci: list[dict], *, max_tokens: int) -> str:
        try:
            async with self._klient(self._timeout()) as klient:
                odpowiedz = await klient.post(f'{self.url}/chat/completions',
                                              json=self._payload(wiadomosci, max_tokens, stream=False))
        except httpx.HTTPError as blad:
            raise _blad_polaczenia(blad, self.url) from blad
        _sprawdz_status(odpowiedz)
        try:
            return odpowiedz.json()['choices'][0]['message']['content'] or ''
        except (KeyError, IndexError, TypeError, ValueError) as blad:
            raise BladAI('LM Studio zwróciło nieoczekiwaną odpowiedź.') from blad

    async def _strumien(self, wiadomosci: list[dict], *, max_tokens: int) -> AsyncIterator[str]:
        try:
            async with self._klient(self._timeout()) as klient:
                async with klient.stream('POST', f'{self.url}/chat/completions',
                                         json=self._payload(wiadomosci, max_tokens, stream=True)) as odpowiedz:
                    if odpowiedz.status_code >= 400:
                        await odpowiedz.aread()
                        _sprawdz_status(odpowiedz)
                    async for linia in odpowiedz.aiter_lines():
                        kawalek = _kawalek_sse(linia)
                        if kawalek is None:
                            break
                        if kawalek:
                            yield kawalek
        except httpx.HTTPError as blad:
            raise _blad_polaczenia(blad, self.url) from blad

    async def _pobierz_kontekst(self) -> int | None:
        """Okno kontekstu załadowanego modelu (REST API LM Studio); None, jeśli serwer go nie podaje."""
        if self._kontekst:
            return self._kontekst
        adres = re.sub(r'/v1$', '', self.url) + f'/api/v0/models/{self.model}'
        try:
            async with self._klient(httpx.Timeout(3.0)) as klient:
                odpowiedz = await klient.get(adres)
            if odpowiedz.status_code == 200:
                self._kontekst = odpowiedz.json().get('loaded_context_length') or None
        except (httpx.HTTPError, ValueError):
            pass
        return self._kontekst

    async def _limit_znakow(self, max_tokens_odpowiedzi: int) -> int:
        """Ile znaków tekstu zmieści się w oknie kontekstu razem z promptem i odpowiedzią."""
        kontekst = await self._pobierz_kontekst()
        if not kontekst:
            return self.limit_znakow
        dostepne_tokeny = kontekst - max_tokens_odpowiedzi - REZERWA_NA_PROMPT
        return max(1000, min(self.limit_znakow, int(dostepne_tokeny * ZNAKOW_NA_TOKEN)))


# --- funkcje pomocnicze (testowane osobno) ---------------------------------------------

def wyciagnij_json(odpowiedz: str) -> dict:
    """Wyciąga obiekt JSON z odpowiedzi modelu (toleruje bloki ```json i tekst dookoła)."""
    tekst = re.sub(r'```(?:json)?', '', odpowiedz).strip()
    poczatek, koniec = tekst.find('{'), tekst.rfind('}')
    if poczatek == -1 or koniec <= poczatek:
        raise BladAI('Bielik zwrócił odpowiedź w niepoprawnym formacie. Spróbuj ponownie.')
    fragment = tekst[poczatek:koniec + 1]
    try:
        dane = json.loads(fragment)
    except json.JSONDecodeError:
        try:
            dane = json.loads(re.sub(r',\s*([}\]])', r'\1', fragment))  # przecinek przed nawiasem
        except json.JSONDecodeError as blad:
            log.warning('Niepoprawny JSON od modelu: %s', odpowiedz[:500])
            raise BladAI('Bielik zwrócił odpowiedź w niepoprawnym formacie. Spróbuj ponownie.') from blad
    if not isinstance(dane, dict):
        raise BladAI('Bielik zwrócił odpowiedź w niepoprawnym formacie. Spróbuj ponownie.')
    return dane


_SLOWO_IMIENIA = re.compile(r'[^\W\d_]+(?:-[^\W\d_]+)*')  # litery, ewentualnie z łącznikiem (Nowak-Kowalska)
_NIE_DANE_OSOBOWE = re.compile(r'^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}(?:\s?r\.?)?$|zł|PLN', re.IGNORECASE)


def dopasuj_w_tekscie(kandydat: str, tekst: str) -> list[str]:
    """Wystąpienia kandydata w tekście: dosłowne oraz – dla imion i nazwisk – w innej formie fleksyjnej.

    „Jan Testowy” znajdzie też „Janie Testowy” i „Jana Testowego” (porównanie po rdzeniu słowa).
    Daty i kwoty pomijamy – to nie są dane osobowe.
    """
    if len(kandydat) < 2 or _NIE_DANE_OSOBOWE.search(kandydat):
        return []
    wynik = [kandydat] if kandydat in tekst else []
    slowa = kandydat.split()
    if slowa and all(_SLOWO_IMIENIA.fullmatch(s) for s in slowa):
        wzorzec = r'(?<!\w)' + r'\s+'.join(
            re.escape(s[:max(3, len(s) - 2)]) + r'[^\W\d_]*' for s in slowa) + r'(?!\w)'
        for dopasowanie in re.finditer(wzorzec, tekst):
            if dopasowanie.group() not in wynik:
                wynik.append(dopasowanie.group())
    return wynik


def _do_porownania(tekst: str) -> str:
    tekst = re.sub(r'[„”“"«»]', '"', tekst.lower())
    tekst = re.sub(r'[–—]', '-', tekst)
    return re.sub(r'\s+', ' ', tekst).strip()


def fragment_w_tekscie(fragment: str, tekst: str, prog: float = 0.75) -> bool:
    """Czy cytat od modelu naprawdę jest w tekście (toleruje inne cudzysłowy, myślniki i drobne różnice)."""
    fragment, tekst = _do_porownania(fragment), _do_porownania(tekst)
    if len(fragment) < 4:
        return False
    if fragment in tekst:
        return True
    slowa = [s for s in re.findall(r'\w+', fragment) if len(s) >= 3]
    slowa_tekstu = set(re.findall(r'\w+', tekst))
    return len(slowa) >= 3 and sum(s in slowa_tekstu for s in slowa) / len(slowa) >= prog


def usun_markdown(tekst: str) -> str:
    """Usuwa formatowanie Markdown, które model czasem dodaje mimo instrukcji (pismo ma być zwykłym tekstem)."""
    tekst = re.sub(r'\*\*(.+?)\*\*', r'\1', tekst, flags=re.S)
    tekst = re.sub(r'(?m)^[ \t]{0,3}#{1,6}[ \t]+', '', tekst)
    tekst = re.sub(r'(?m)^[ \t]*[-*_]{3,}[ \t]*$', '', tekst)
    return re.sub(r'\n{3,}', '\n\n', tekst).strip()


def podziel_tekst(tekst: str, limit: int) -> list[str]:
    """Dzieli tekst na części do `limit` znaków, najlepiej na granicy akapitu lub linii."""
    czesci = []
    while len(tekst) > limit:
        for separator in ('\n\n', '\n', ' '):  # akapit > linia > słowo, byle nie w pierwszej połowie
            ciecie = tekst.rfind(separator, 0, limit)
            if ciecie >= limit // 2:
                break
        else:
            ciecie = limit
        ciecie = max(ciecie, 1)
        czesci.append(tekst[:ciecie])
        tekst = tekst[ciecie:].lstrip()
    if tekst.strip():
        czesci.append(tekst)
    return czesci


def przytnij_do_budzetu(limit: int, wniosek: str, informacje: str, wzor: str | None) -> tuple[str, str, str | None]:
    """Rozdziela limit znaków: informacje z wydziałów są najważniejsze, wniosek i wzór dostają mniej."""
    limit_wzoru = int(limit * 0.2) if wzor else 0
    limit_wniosku = int(limit * 0.3)
    wniosek = wniosek[:limit_wniosku]
    wzor = wzor[:limit_wzoru] if wzor else None
    informacje = informacje[:limit - len(wniosek) - len(wzor or '')]
    return wniosek, informacje, wzor


def _kawalek_sse(linia: str) -> str | None:
    """Treść z linii strumienia SSE. None oznacza koniec strumienia, '' – linię bez treści."""
    if not linia.startswith('data:'):
        return ''
    dane = linia[5:].strip()
    if dane == '[DONE]':
        return None
    try:
        return json.loads(dane)['choices'][0].get('delta', {}).get('content') or ''
    except (ValueError, KeyError, IndexError, TypeError):
        return ''


def _na_bool(wartosc: object) -> bool:
    if isinstance(wartosc, bool):
        return wartosc
    return str(wartosc).strip().lower() in ('true', 'tak', 'yes', '1')


def _sprawdz_status(odpowiedz: httpx.Response) -> None:
    if odpowiedz.status_code < 400:
        return
    try:
        blad = odpowiedz.json().get('error')
        komunikat = blad.get('message') if isinstance(blad, dict) else str(blad)
    except ValueError:
        komunikat = odpowiedz.text[:300]
    log.warning('LM Studio HTTP %s: %s', odpowiedz.status_code, komunikat)
    if any(slowo in (komunikat or '').lower() for slowo in ('context', 'n_ctx', 'too long', 'exceeds')):
        raise BladAI('Tekst jest za długi dla okna kontekstu modelu. Zwiększ „Context Length” w LM Studio '
                     'albo zmniejsz limit znaków (UDIP_LLM_LIMIT_ZNAKOW).')
    raise BladAI(f'LM Studio zwróciło błąd: {komunikat}')


def _blad_polaczenia(blad: httpx.HTTPError, url: str) -> BladAI:
    if isinstance(blad, httpx.TimeoutException):
        return BladAI(f'Bielik nie odpowiedział w ciągu {CZAS_ODPOWIEDZI:.0f} s. Spróbuj ponownie lub skróć tekst.')
    if isinstance(blad, httpx.ConnectError):
        return BladAI(f'Brak połączenia z Bielikiem ({url}). Uruchom LM Studio i włącz serwer lokalny.')
    return BladAI(f'Błąd komunikacji z Bielikiem: {blad}')
