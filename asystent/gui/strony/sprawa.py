"""Widok sprawy: kolejne kroki od wniosku do wysłanej odpowiedzi."""

import shutil
from collections.abc import Callable
from contextlib import aclosing
from datetime import date, datetime, timedelta
from pathlib import Path

from nicegui import app, run, ui

from ... import rejestr, stan_sprawy
from ...ai import BladAI, usun_markdown
from ...ai.wydzialy import dobierz, nazwy_wydzialow
from ...anonimizacja import podziel_na_fragmenty, wykryj_wzorce, zamaskuj
from ...kontrola import WynikKontroli, sprawdz_pismo
from ...pliki import FORMATY, Kategoria, ZapisanyPlik, eksportuj, nazwa_pliku_odpowiedzi
from ...rejestr import Wniosek
from ...uslugi import bielik, magazyn
from ..komponenty import (WgranePliki, blad_ai, karta_pliku, naglowek_strony, odmiana, otworz_w_systemie,
                          potwierdz, strefa_wgrywania, todo, wskaznik_postepu, zapisz_wgrane)
from ..kontekst import biezacy
from .wnioski import KOLOR_STATUSU

# Wyszukiwanie w archiwum to osobny moduł – na razie dane przykładowe.
PODOBNE_SPRAWY = [
    ('UDIP.112.2025', 'Wydatki na promocję miasta w 2024 r.', 'Biuro Komunikacji Społecznej', '12.03.2025', 92),
    ('UDIP.87.2025', 'Budżet kampanii reklamowych miasta', 'Wydział Finansów', '02.02.2025', 78),
    ('UDIP.240.2024', 'Umowy z agencjami PR', 'Wydział Zamówień Publicznych', '18.10.2024', 64),
]

PROJEKT_ODPOWIEDZI = (
    'Szanowny Panie,\n\n'
    'w odpowiedzi na wniosek o udostępnienie informacji publicznej z dnia {wplyw} '
    'uprzejmie informuję, że [UZUPEŁNIĆ – albo kliknij „Generuj projekt”].\n\n'
    'Podstawa prawna: art. 2 ust. 1 i art. 10 ust. 1 ustawy z dnia 6 września 2001 r. '
    'o dostępie do informacji publicznej.\n\n'
    'Z poważaniem'
)

Odswiezacz = Callable[[], None] | None


def _awansuj(w: Wniosek, status: str, powod: str, po_zmianie: Callable[[], None]) -> None:
    """Automatyczna zmiana statusu po czynności urzędnika (tylko do przodu) z krótką informacją."""
    if rejestr.awansuj_status(w, status, powod):
        ui.notify(f'Status sprawy: {w.status_opis}.', type='info', icon='flag')
        po_zmianie()


def _tekst_wniosku(w: Wniosek) -> str:
    pliki = magazyn.lista(Kategoria.WNIOSEK, sprawa=w.nr)
    return pliki[0].tekst() if pliki else ''


# --- krok 1: wniosek -----------------------------------------------------------------

def _krok_wniosek(w: Wniosek) -> Odswiezacz:
    @ui.refreshable
    def dane_i_przebieg() -> None:
        with ui.row().classes('w-full items-start no-wrap gap-8'):
            with ui.grid(columns=2).classes('gap-x-8 gap-y-1'):
                termin = f'{w.termin:%d.%m.%Y}' + (f' (kwerenda +{w.dni_kwerendy} dni)' if w.kwerenda else '')
                for etykieta, wartosc in [('Wnioskodawca', w.wnioskodawca), ('Kontakt', w.kontakt or '—'),
                                          ('Data wpływu', f'{w.data_wplywu:%d.%m.%Y}'), ('Termin', termin),
                                          ('Prowadzi', w.kto), ('Status', w.status_opis),
                                          ('Data odpowiedzi', f'{w.data_odpowiedzi:%d.%m.%Y}' if w.data_odpowiedzi
                                           else '—')]:
                    ui.label(etykieta).classes('text-grey-7')
                    ui.label(wartosc)
                if w.uwaga_o_terminie:
                    ui.label('')
                    ui.label(w.uwaga_o_terminie).classes('text-caption text-grey-7')
            with ui.expansion('Przebieg sprawy', icon='history', value=True).props('dense').classes('col'):
                with ui.timeline(side='right').props('dense color=primary layout=dense'):
                    for wpis in reversed(w.historia):
                        kiedy = wpis['kiedy'].replace('T', ' ')
                        ui.timeline_entry(wpis['zdarzenie'],
                                          subtitle=f'{kiedy[8:10]}.{kiedy[5:7]}.{kiedy[:4]} {kiedy[11:16]}')

    dane_i_przebieg()
    ui.separator().classes('my-2')

    async def wgraj(pliki: WgranePliki) -> None:
        if await zapisz_wgrane(pliki[:1], lambda n, d: magazyn.zapisz(d, n, Kategoria.WNIOSEK, sprawa=w.nr)):
            pliki_wniosku.refresh()

    async def usun(plik: ZapisanyPlik) -> None:
        await run.io_bound(magazyn.usun, plik)
        pliki_wniosku.refresh()

    @ui.refreshable
    def pliki_wniosku() -> None:
        pliki = magazyn.lista(Kategoria.WNIOSEK, sprawa=w.nr)
        if pliki:
            for plik in pliki:
                karta_pliku(plik, on_usun=usun, pokaz_tekst=True)
        else:
            ui.label('Do tej sprawy nie wgrano jeszcze pliku wniosku.').classes('text-grey-7')
            strefa_wgrywania(wgraj, tytul='Przeciągnij tutaj plik wniosku')

    pliki_wniosku()
    return dane_i_przebieg.refresh


# --- krok 2: podobne sprawy -----------------------------------------------------------

def _krok_podobne() -> Odswiezacz:
    ui.label('Podobne sprawy z archiwum').classes('text-weight-medium')
    ui.label('TODO: wyszukiwanie w archiwum – poniżej dane przykładowe.').classes('text-caption text-grey-7')
    for nr, temat, wydzial, data, podobienstwo in PODOBNE_SPRAWY:
        with ui.card().classes('w-full').props('flat bordered'):
            with ui.row().classes('w-full items-center justify-between no-wrap'):
                with ui.column().classes('gap-0'):
                    ui.label(f'{nr} – {temat}').classes('text-weight-medium')
                    ui.label(f'{wydzial} · {data}').classes('text-caption text-grey-7')
                with ui.row().classes('items-center no-wrap'):
                    ui.linear_progress(podobienstwo / 100, show_value=False).classes('w-32')
                    ui.label(f'{podobienstwo}%').classes('w-10')
                    ui.button('Otwórz', on_click=todo('podgląd sprawy archiwalnej')).props('flat dense')
    return None


# --- krok 3: wydziały ---------------------------------------------------------------

def _krok_wydzialy(w: Wniosek) -> Odswiezacz:
    async def zaproponuj() -> None:
        tekst = _tekst_wniosku(w)
        if not tekst.strip():
            ui.notify('Najpierw wgraj plik wniosku (krok „Wniosek”).', type='warning')
            return
        przycisk.props('loading')
        postep.set_visibility(True)
        try:
            dobor = await run.io_bound(dobierz, tekst)
        finally:
            if not przycisk.is_deleted:
                przycisk.props(remove='loading')
                postep.set_visibility(False)
        if not dobor.propozycje:
            if not przycisk.is_deleted:
                ui.notify(dobor.komunikat or 'Nie dopasowano wydziału – wybierz go z listy.', type='warning')
            return
        w.sugerowane_wydzialy = dobor.etykiety
        w.uzasadnienie_wydzialu = dobor.uzasadnienie
        rejestr.zapisz_zmiany()
        if przycisk.is_deleted:  # urzędnik wyszedł ze sprawy – wynik i tak zapisany
            return
        if dobor.komunikat:  # np. LM Studio wyłączone – wynik z samych słów kluczowych
            ui.notify(dobor.komunikat, type='warning')
        propozycje.refresh()

    def zmien_wybor(zdarzenie) -> None:
        w.sugerowane_wydzialy = list(zdarzenie.value or [])
        rejestr.zapisz_zmiany()
        uzasadnienia.refresh()  # samo pole wyboru zostaje – lista się nie zamyka

    async def kopiuj() -> None:
        await ui.clipboard.write(prosba.value)
        ui.notify('Skopiowano treść prośby do schowka.', type='positive')

    with ui.row().classes('w-full items-center justify-between'):
        ui.label('Wydziały, do których kierujesz prośbę').classes('text-weight-medium')
        przycisk = ui.button('Zaproponuj (Bielik)', icon='auto_awesome', on_click=zaproponuj).props('flat dense')
    postep = wskaznik_postepu('Bielik dobiera wydziały z listy BIP… zwykle 30–60 s.')

    @ui.refreshable
    def propozycje() -> None:
        wszystkie = nazwy_wydzialow()
        opcje = wszystkie + [n for n in w.sugerowane_wydzialy if n not in wszystkie]  # starsze wpisy spoza listy
        ui.select(opcje, multiple=True, value=list(w.sugerowane_wydzialy), with_input=True, on_change=zmien_wybor,
                  label='Wydziały (wykaz z BIP – możesz dodać i usunąć)').props('use-chips').classes('w-full')
        uzasadnienia()

    @ui.refreshable
    def uzasadnienia() -> None:
        if not w.sugerowane_wydzialy:
            ui.label('Kliknij „Zaproponuj” albo wybierz wydziały z listy.').classes('text-grey-7')
            return
        wybrane = ' '.join(w.sugerowane_wydzialy)
        for linia in w.uzasadnienie_wydzialu.splitlines():  # „SKRÓT – dlaczego”; tylko dla wybranych wydziałów
            skrot = linia.split(' – ', 1)[0]
            if f'({skrot})' in wybrane or ' – ' not in linia:
                ui.label(linia).classes('text-caption text-grey-8')
        ui.label('Podpowiedź asystenta – sprawdź przed wysłaniem prośby.').classes('text-caption text-grey-6')

    propozycje()
    termin_wydzialu = max(w.termin - timedelta(days=3), date.today())
    prosba = ui.textarea('Treść prośby do wydziałów', value=(
        f'Uprzejmie proszę o przygotowanie informacji niezbędnych do udzielenia odpowiedzi na wniosek {w.nr} '
        f'dotyczący: {w.temat}.\nProszę o przekazanie informacji do dnia {termin_wydzialu:%d.%m.%Y}.'
    )).classes('w-full').props('autogrow')
    with ui.row():
        ui.button('Kopiuj treść', icon='content_copy', on_click=kopiuj).props('outline')
        ui.label('Asystent niczego nie wysyła – prośbę wysyłasz sam.').classes('text-caption text-grey-7 self-center')
    return propozycje.refresh


# --- krok 4: odpowiedzi wydziałów ------------------------------------------------------

def _krok_odpowiedzi(w: Wniosek, po_zmianie_statusu: Callable[[], None]) -> Odswiezacz:
    ui.label('Odpowiedzi z wydziałów').classes('text-weight-medium')
    with ui.row().classes('w-full items-start no-wrap gap-6'):
        with ui.column().classes('w-[26rem] shrink-0'):
            sugerowane = list(w.sugerowane_wydzialy)  # najpierw te, do których poszła prośba, potem reszta z BIP
            wydzial = ui.select(sugerowane + [n for n in nazwy_wydzialow() if n not in sugerowane],
                                label='Od którego wydziału? (opcjonalnie)',
                                with_input=True, new_value_mode='add-unique', clearable=True).classes('w-full')
            strefa_wgrywania(lambda pliki: wgraj(pliki), tytul='Przeciągnij tutaj odpowiedzi wydziałów', wiele=True)
        lista = ui.column().classes('col')

    async def wgraj(pliki: WgranePliki) -> None:
        zapis = lambda n, d: magazyn.zapisz(d, n, Kategoria.ODPOWIEDZ_WYDZIALU, sprawa=w.nr, opis=wydzial.value)
        if await zapisz_wgrane(pliki, zapis):
            odpowiedzi.refresh()
            _awansuj(w, 'wydzialy', 'wgrano odpowiedź wydziału', po_zmianie_statusu)

    async def usun(plik: ZapisanyPlik) -> None:
        await run.io_bound(magazyn.usun, plik)
        odpowiedzi.refresh()

    @ui.refreshable
    def odpowiedzi() -> None:
        pliki = magazyn.lista(Kategoria.ODPOWIEDZ_WYDZIALU, sprawa=w.nr)
        if not pliki:
            ui.label('Brak wgranych odpowiedzi.').classes('text-grey-7')
        for plik in pliki:
            karta_pliku(plik, on_usun=usun)

    with lista:
        odpowiedzi()
    return None


# --- krok 5: projekt odpowiedzi (generowany na żywo) ---------------------------------------

def _krok_projekt(w: Wniosek, stan: dict) -> Odswiezacz:
    archiwum = magazyn.lista(Kategoria.ARCHIWUM)

    async def generuj() -> None:
        odpowiedzi = magazyn.lista(Kategoria.ODPOWIEDZ_WYDZIALU, sprawa=w.nr)
        if not odpowiedzi:
            ui.notify('Brak odpowiedzi wydziałów – Bielik wstawi pola [UZUPEŁNIĆ].', type='warning')
        if stan['projekt'].strip() and stan['projekt'] != stan['szablon'] \
                and not await potwierdz('Zastąpić obecną treść projektu nowym projektem?', 'Zastąp'):
            return

        tekst_wniosku = _tekst_wniosku(w) or f'Wniosek dotyczy: {w.temat}. Wnioskodawca: {w.wnioskodawca}.'
        informacje = '\n\n'.join(f'[{p.opis or p.nazwa_oryginalna}]\n{p.tekst()}' for p in odpowiedzi) \
            or '(wydziały nie przekazały jeszcze informacji)'
        wzor = next((p.tekst() for p in archiwum if p.plik == wybor_wzoru.value), None)

        stan.update(projekt='', ukryte=set(), wykryte={}, generowanie=True)
        przycisk_generuj.set_visibility(False)
        przycisk_stop.set_visibility(True)
        postep.set_visibility(True)
        try:
            async with aclosing(bielik.generuj_odpowiedz(wniosek=tekst_wniosku, informacje_wydzialow=informacje,
                                                         wzor=wzor)) as strumien:
                async for kawalek in strumien:
                    stan['projekt'] += kawalek
                    if not stan['generowanie']:
                        ui.notify('Zatrzymano generowanie.', type='info')
                        break
        except BladAI as blad:
            blad_ai(str(blad))
            if not stan['projekt']:
                stan['projekt'] = stan['szablon']
        finally:
            stan['projekt'] = usun_markdown(stan['projekt'])
            stan['generowanie'] = False
            przycisk_generuj.set_visibility(True)
            przycisk_stop.set_visibility(False)
            postep.set_visibility(False)
        if stan['projekt'] != stan['szablon']:
            kontrola.sprawdz_bez_ai()  # od razu pokazujemy liczby bez pokrycia i braki

    with ui.row().classes('w-full items-center justify-between'):
        ui.label('Projekt odpowiedzi').classes('text-weight-medium')
        with ui.row().classes('items-center'):
            wybor_wzoru = ui.select({p.plik: p.nazwa_oryginalna for p in archiwum},
                                    label='Wzór z archiwum (opcjonalnie)', clearable=True).classes('w-72')
            przycisk_generuj = ui.button('Generuj projekt (Bielik)', icon='auto_awesome', on_click=generuj)
            przycisk_stop = ui.button('Zatrzymaj', icon='stop',
                                      on_click=lambda: stan.update(generowanie=False)).props('outline color=negative')
            przycisk_stop.set_visibility(False)
    postep = wskaznik_postepu('Bielik pisze projekt na podstawie wniosku i odpowiedzi wydziałów… (ok. 1–2 min)')
    ui.textarea().bind_value(stan, 'projekt').classes('w-full').props('outlined autogrow')
    ui.label('Sprawdź treść merytorycznie – projekt przygotowuje AI, decyzja należy do Ciebie. '
             'Pola [UZUPEŁNIĆ] wymagają uzupełnienia.').classes('text-caption text-grey-7')
    kontrola = PanelKontroli(w, stan)
    return kontrola.odswiez


# --- kontrola jakości pisma ---------------------------------------------------------------

def _zrodla(w: Wniosek, kategoria: Kategoria) -> list[tuple[str, str]]:
    """Teksty, z których pismo czerpie liczby i daty (nazwa pliku albo wydziału, tekst)."""
    return [(p.opis or p.nazwa_oryginalna, p.tekst()) for p in magazyn.lista(kategoria, sprawa=w.nr)]


def _dane_sprawy(w: Wniosek) -> list[str]:
    return [w.nr, f'{w.data_wplywu:%d.%m.%Y}', f'{w.termin:%d.%m.%Y}', f'{date.today():%d.%m.%Y}']


class PanelKontroli:
    """Kontrola jakości projektu: liczby i daty ze źródłami, braki, forma (od razu) i kompletność (Bielik)."""

    def __init__(self, w: Wniosek, stan: dict) -> None:
        self.w, self.stan = w, stan
        stan.setdefault('kontrola', None)
        stan.setdefault('kompletnosc', None)
        with ui.card().props('flat bordered').classes('w-full q-mt-md'):
            with ui.row().classes('w-full items-center justify-between no-wrap'):
                with ui.column().classes('gap-0'):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('fact_check', color='primary')
                        ui.label('Kontrola jakości').classes('text-subtitle1 text-weight-medium')
                    ui.label('Każda liczba i data musi mieć pokrycie we wniosku albo w odpowiedziach wydziałów.') \
                        .classes('text-caption text-grey-7')
                self.przycisk = ui.button('Sprawdź pismo', icon='fact_check', on_click=self.sprawdz).props('outline')
            self.wyniki = ui.column().classes('w-full gap-2')
        self.odswiez()

    def sprawdz_bez_ai(self) -> None:
        self.stan['kontrola'] = sprawdz_pismo(
            self.stan['projekt'], _zrodla(self.w, Kategoria.WNIOSEK),
            do_pokrycia=_zrodla(self.w, Kategoria.ODPOWIEDZ_WYDZIALU),
            ukryte=self.stan['ukryte'], dane_sprawy=_dane_sprawy(self.w))
        self.stan['kontrola_tekst'] = self.stan['projekt']
        self.stan['kompletnosc'] = None
        self.odswiez()

    async def sprawdz(self) -> None:
        self.sprawdz_bez_ai()
        tekst_wniosku = _tekst_wniosku(self.w)
        if not tekst_wniosku.strip():
            self.stan['kompletnosc'] = 'Brak pliku wniosku – nie da się sprawdzić, czy pismo odpowiada na żądania.'
            self.odswiez()
            return
        self.stan['kompletnosc'] = 'trwa'
        self.przycisk.props('loading')
        self.odswiez()
        try:
            self.stan['kompletnosc'] = await bielik.sprawdz_kompletnosc(tekst_wniosku, self.stan['projekt'])
        except BladAI as blad:
            self.stan['kompletnosc'] = f'Kompletności nie sprawdzono: {blad}'
        finally:
            self.przycisk.props(remove='loading')
        self.odswiez()

    def odswiez(self) -> None:
        if self.wyniki.is_deleted:  # urzędnik wyszedł ze sprawy, zanim Bielik skończył
            return
        self.wyniki.clear()
        with self.wyniki:
            self._rysuj()

    def _rysuj(self) -> None:
        wynik: WynikKontroli | None = self.stan['kontrola']
        if wynik is None:
            ui.label('Kliknij „Sprawdź pismo” – liczby, daty i braki sprawdzę od razu, a Bielik oceni, czy pismo '
                     'odpowiada na wszystkie żądania wnioskodawcy.').classes('text-grey-7')
            return
        if self.stan.get('kontrola_tekst') != self.stan['projekt']:
            with ui.row().classes('items-center gap-1 text-orange-9'):
                ui.icon('update', size='xs')
                ui.label('Treść zmieniła się od ostatniej kontroli – sprawdź ponownie.').classes('text-caption')

        with ui.row().classes('gap-2'):
            _plakietka(f'{len(wynik.bledy)} do poprawy', 'red' if wynik.bledy else 'green', 'error_outline')
            _plakietka(f'{len(wynik.ostrzezenia)} ostrzeżeń', 'orange' if wynik.ostrzezenia else 'green',
                       'warning_amber')
            _plakietka(f'{len(wynik.potwierdzone)} wartości potwierdzonych w źródłach', 'green', 'verified')

        self._podglad(wynik)
        for problem in wynik.problemy:
            blad = problem.waga == 'blad'
            with ui.row().classes('items-start no-wrap gap-2'):
                ui.icon('error_outline' if blad else 'warning_amber', color='red-7' if blad else 'orange-8',
                        size='xs').classes('q-mt-xs')
                ui.label(problem.opis).classes('text-body2')
        self._kompletnosc()

    def _podglad(self, wynik: WynikKontroli) -> None:
        """Pismo z zaznaczonymi wartościami: zielone – mają źródło, czerwone – brak pokrycia."""
        oznaczenia: dict[str, tuple[str, str]] = {}
        for wartosc in wynik.wartosci:
            if wartosc.zrodlo:
                oznaczenia.setdefault(wartosc.tekst, ('bg-green-2 text-green-10', f'Źródło: {wartosc.zrodlo}'))
            else:
                oznaczenia[wartosc.tekst] = ('bg-red-3 text-red-10', 'Brak w źródłach – sprawdź!')
        for problem in wynik.bledy:
            if problem.fragment.startswith('['):
                oznaczenia[problem.fragment] = ('bg-orange-3 text-orange-10', 'Do uzupełnienia')
        tekst = self.stan.get('kontrola_tekst') or ''
        with ui.expansion('Podgląd pisma z zaznaczonymi wartościami', icon='visibility', value=True) \
                .props('dense').classes('w-full'):
            with ui.element('div').classes('text-body2 q-pa-sm bg-grey-1 rounded-borders') \
                    .style('white-space: pre-wrap; line-height: 1.9'):
                for fragment, zaznaczony in podziel_na_fragmenty(tekst, oznaczenia):
                    if not zaznaczony:
                        ui.label(fragment).classes('inline')
                        continue
                    klasy, opis = oznaczenia[fragment]
                    ui.label(fragment).classes(f'inline px-1 rounded-borders {klasy}').tooltip(opis)

    def _kompletnosc(self) -> None:
        kompletnosc = self.stan['kompletnosc']
        if kompletnosc is None:
            return
        ui.separator()
        ui.label('Czy pismo odpowiada na wszystkie żądania? (Bielik)').classes('text-weight-medium')
        if kompletnosc == 'trwa':
            with ui.row().classes('items-center gap-2 text-primary'):
                ui.spinner(size='sm')
                ui.label('Bielik porównuje pismo z wnioskiem… zwykle ok. 1 min.').classes('text-caption')
            return
        if isinstance(kompletnosc, str):
            ui.label(kompletnosc).classes('text-caption text-orange-9')
            return
        for zadanie in kompletnosc:
            with ui.row().classes('items-start no-wrap gap-2'):
                ui.icon('check_circle' if zadanie.odpowiedziano else 'cancel',
                        color='green-7' if zadanie.odpowiedziano else 'red-7', size='xs').classes('q-mt-xs')
                with ui.column().classes('gap-0'):
                    ui.label(zadanie.tresc).classes('text-body2')
                    ui.label(f'„{zadanie.fragment}”' if zadanie.odpowiedziano else 'brak odpowiedzi w piśmie') \
                        .classes('text-caption ' + ('text-grey-7' if zadanie.odpowiedziano else 'text-red-7'))


def _plakietka(tekst: str, kolor: str, ikona: str) -> None:
    ui.chip(tekst, icon=ikona).props(f'dense square color={kolor}-1 text-color={kolor}-9')


# --- krok 6: anonimizacja --------------------------------------------------------------

def _krok_anonimizacja(stan: dict) -> Odswiezacz:
    async def wykryj() -> None:
        tekst = stan['projekt']
        if not tekst.strip():
            ui.notify('Projekt odpowiedzi jest pusty.', type='warning')
            return
        przycisk.props('loading')
        postep.set_visibility(True)
        wykryte = dict(wykryj_wzorce(tekst))
        try:
            for ciag in await bielik.wykryj_dane_osobowe(tekst):
                wykryte.setdefault(ciag, 'Dane osobowe (Bielik)')
        except BladAI as blad:
            blad_ai(f'Bielik niedostępny – pokazuję tylko dane wykryte wzorcami (PESEL, telefon, e-mail…). {blad}')
        finally:
            przycisk.props(remove='loading')
            postep.set_visibility(False)
        stan['wykryte'] = {**wykryte, **{c: t for c, t in stan['wykryte'].items() if t == 'Dodane ręcznie'}}
        widok.refresh()
        ui.notify(f'Znaleziono {odmiana(len(wykryte), "fragment", "fragmenty", "fragmentów")} do sprawdzenia.')

    def przelacz(ciag: str) -> None:
        stan['ukryte'] ^= {ciag}
        widok.refresh()

    def zatwierdz_wszystkie() -> None:
        stan['ukryte'] |= set(stan['wykryte'])
        widok.refresh()

    def dodaj_recznie() -> None:
        ciag = (reczny.value or '').strip()
        if not ciag or ciag not in stan['projekt']:
            ui.notify('Nie ma takiego fragmentu w projekcie – przepisz go dokładnie.', type='warning')
            return
        stan['wykryte'][ciag] = 'Dodane ręcznie'
        stan['ukryte'].add(ciag)
        reczny.value = ''
        widok.refresh()

    @ui.refreshable
    def widok() -> None:
        tekst = stan['projekt']
        obecne = {c for c in stan['wykryte'] if c in tekst}
        stan['ukryte'] &= obecne
        with ui.card().classes('w-full').props('flat bordered'):
            with ui.element('div').classes('text-body1').style('line-height: 2; white-space: pre-wrap'):
                for fragment, dane in podziel_na_fragmenty(tekst, obecne):
                    if not dane:
                        ui.label(fragment).classes('inline')
                        continue
                    ukryty = fragment in stan['ukryte']
                    pole = ui.label(fragment).classes('inline px-1 rounded-borders cursor-pointer ' +
                                                      ('bg-black text-black' if ukryty else 'bg-grey-4'))
                    pole.tooltip(f'{stan["wykryte"].get(fragment, "")} – kliknij, żeby '
                                 f'{"odkryć" if ukryty else "ukryć"}')
                    pole.on('click', lambda _, f=fragment: przelacz(f))
        info.set_text(f'Do ukrycia: {len(stan["ukryte"])} z {len(obecne)} wskazanych')

    with ui.row().classes('w-full no-wrap gap-6 items-start'):
        kontener = ui.column().classes('col')

        with ui.column().classes('w-72 shrink-0'):
            info = ui.label().classes('text-weight-medium')
            ui.label('Szare – propozycja asystenta. Czarne – zatwierdzone do ukrycia. '
                     'Kliknij fragment, żeby przełączyć. Ukrywane są wszystkie wystąpienia.') \
                .classes('text-caption text-grey-7')
            przycisk = ui.button('Wykryj dane osobowe', icon='auto_awesome', on_click=wykryj).classes('w-full')
            postep = wskaznik_postepu('Bielik szuka danych osobowych…')
            ui.button('Zatwierdź wszystkie', icon='done_all', on_click=zatwierdz_wszystkie) \
                .props('outline').classes('w-full')
            with ui.row().classes('w-full items-center no-wrap'):
                reczny = ui.input('Ukryj własny fragment').props('dense').classes('col')
                ui.button(icon='add', on_click=dodaj_recznie).props('flat round dense').tooltip('Dodaj do ukrycia')

    with kontener:
        widok()
    return widok.refresh


# --- krok 7: eksport -------------------------------------------------------------------

def _stan_kontroli(stan: dict) -> None:
    """Jedna linijka o kontroli jakości – żeby nie wysłać pisma z błędami."""
    wynik: WynikKontroli | None = stan.get('kontrola')
    kompletnosc = stan.get('kompletnosc')
    braki = [z for z in kompletnosc if not z.odpowiedziano] if isinstance(kompletnosc, list) else []
    if wynik is None:
        kolor, ikona, tekst = 'orange-9', 'warning_amber', 'Nie uruchomiono kontroli jakości – zrób to w kroku „Projekt odpowiedzi”.'
    elif stan.get('kontrola_tekst') != stan['projekt']:
        kolor, ikona, tekst = 'orange-9', 'update', 'Pismo zmieniło się od ostatniej kontroli jakości – sprawdź je ponownie.'
    elif wynik.bledy or braki:
        kolor, ikona = 'red-8', 'error_outline'
        tekst = (f'Kontrola jakości: {odmiana(len(wynik.bledy), "problem", "problemy", "problemów")} do poprawy'
                 + (f', brak odpowiedzi na {odmiana(len(braki), "żądanie", "żądania", "żądań")}' if braki else '')
                 + ' – popraw przed wysłaniem.')
    else:
        kolor, ikona, tekst = 'green-8', 'verified', 'Kontrola jakości bez błędów.'
    with ui.row().classes(f'items-center gap-1 text-{kolor}'):
        ui.icon(ikona)
        ui.label(tekst)

async def _zapisz_pismo(w: Wniosek, tekst: str, format: str) -> Path | None:
    """Zapisuje pismo w dokumentach sprawy, a w trybie okna pyta też, gdzie zapisać kopię."""
    nazwa = nazwa_pliku_odpowiedzi(w.nr, format)
    kopia = await run.io_bound(eksportuj, tekst, magazyn.katalog_eksportu(w.nr) / nazwa)

    okno = app.native.main_window
    if okno is None:  # tryb przeglądarki
        ui.download.file(kopia, nazwa)
        return kopia

    import webview  # dostępne tylko w trybie okna
    wybor = await okno.create_file_dialog(webview.FileDialog.SAVE, save_filename=nazwa,
                                          file_types=(FORMATY[format],))
    if not wybor:
        ui.notify(f'Pismo zapisano w dokumentach sprawy ({nazwa}).', type='positive')
        return kopia
    cel = Path(wybor if isinstance(wybor, str) else wybor[0])
    if cel.suffix.lower() != f'.{format}':
        cel = cel.with_suffix(f'.{format}')
    await run.io_bound(shutil.copyfile, kopia, cel)
    ui.notify(f'Zapisano: {cel}', type='positive')
    return cel


def _krok_eksport(w: Wniosek, stan: dict, po_zmianie_statusu: Callable[[], None]) -> Odswiezacz:
    ui.label('Eksport i zamknięcie sprawy').classes('text-weight-medium')

    @ui.refreshable
    def stan_anonimizacji() -> None:
        _stan_kontroli(stan)
        if stan['ukryte']:
            with ui.row().classes('items-center gap-1 text-green-8'):
                ui.icon('verified_user')
                ui.label('W eksporcie dane osobowe zostaną zamaskowane '
                         f'({odmiana(len(stan["ukryte"]), "fragment", "fragmenty", "fragmentów")}).')
        else:
            with ui.row().classes('items-center gap-1 text-orange-9'):
                ui.icon('warning_amber')
                ui.label('Nie zatwierdzono anonimizacji – sprawdź krok „Anonimizacja” przed wysłaniem.')

    stan_anonimizacji()

    async def zapisz(format: str) -> None:
        if not stan['projekt'].strip():
            ui.notify('Projekt odpowiedzi jest pusty.', type='warning')
            return
        await _zapisz_pismo(w, zamaskuj(stan['projekt'], stan['ukryte']), format)
        eksporty.refresh()
        _awansuj(w, 'przygotowana', f'zapisano pismo (.{format})', po_zmianie_statusu)

    def otworz_folder() -> None:
        katalog = magazyn.katalog_sprawy(w.nr)
        katalog.mkdir(parents=True, exist_ok=True)
        otworz_w_systemie(katalog)

    with ui.row():
        ui.button('Zapisz .docx', icon='description', on_click=lambda: zapisz('docx'))
        ui.button('Zapisz .txt', icon='article', on_click=lambda: zapisz('txt')).props('outline')
        ui.button('Otwórz folder sprawy', icon='folder_open', on_click=otworz_folder).props('flat')

    @ui.refreshable
    def eksporty() -> None:
        katalog = magazyn.katalog_eksportu(w.nr)
        for plik in sorted(katalog.glob('*')) if katalog.exists() else []:
            with ui.row().classes('items-center gap-2'):
                ui.icon('task', color='green-7')
                ui.label(plik.name).classes('text-primary cursor-pointer underline') \
                    .on('click', lambda _, p=plik: otworz_w_systemie(p)).tooltip('Otwórz')

    eksporty()
    ui.separator().classes('my-2')
    ui.label('Aplikacja niczego nie wysyła – po wysłaniu pisma oznacz to tutaj, żeby zamknąć sprawę w kalendarzu.') \
        .classes('text-caption text-grey-7')

    def oznacz_wyslane() -> None:
        try:
            data = date.fromisoformat(data_odpowiedzi.value)
        except (TypeError, ValueError):
            ui.notify('Podaj poprawną datę udzielenia odpowiedzi.', type='warning')
            return
        if data > date.today():
            ui.notify('Data udzielenia odpowiedzi nie może być z przyszłości.', type='warning')
            return
        if rejestr.zmien_status(w, 'wyslana', data_odpowiedzi=data, powod='oznaczono po wysłaniu pisma'):
            ui.notify(f'Sprawa {w.nr} zamknięta – odpowiedź wysłana {data:%d.%m.%Y}.', type='positive')
            po_zmianie_statusu()

    with ui.row().classes('items-center'):
        data_odpowiedzi = ui.date_input('Data udzielenia odpowiedzi',
                                        value=(w.data_odpowiedzi or date.today()).isoformat())
        ui.button('Oznacz jako wysłane', icon='mark_email_read', color='positive', on_click=oznacz_wyslane)
    return stan_anonimizacji.refresh


# --- status, edycja, kwerenda, usuwanie --------------------------------------------------

IKONY_STATUSOW = {'brak': 'radio_button_unchecked', 'wydzialy': 'forward_to_inbox', 'przygotowana': 'edit_document',
                  'wyslana': 'mark_email_read'}


def _przycisk_statusu(w: Wniosek, po_zmianie: Callable[[], None]) -> None:
    """Status jako przycisk z menu – urzędnik może go zmienić ręcznie (także cofnąć)."""

    async def zmien(kod: str) -> None:
        data = None
        if kod == 'wyslana':
            data = await _zapytaj_o_date('Kiedy wysłano odpowiedź?', w.data_odpowiedzi or date.today())
            if data is None:
                return
        if rejestr.zmien_status(w, kod, data_odpowiedzi=data, powod='zmiana ręczna'):
            ui.notify(f'Status sprawy: {w.status_opis}.', type='positive')
            po_zmianie()

    with ui.button(w.status_opis, icon=IKONY_STATUSOW[w.status]) \
            .props(f'unelevated no-caps color={KOLOR_STATUSU[w.status]}').tooltip('Zmień status'):
        with ui.menu():
            for kod, opis in rejestr.STATUSY.items():
                with ui.item(on_click=lambda k=kod: zmien(k)):
                    with ui.item_section().props('avatar'):
                        ui.icon('check' if kod == w.status else IKONY_STATUSOW[kod],
                                color='primary' if kod == w.status else 'grey-7')
                    with ui.item_section():
                        ui.item_label(opis)


async def _zapytaj_o_date(pytanie: str, domyslna: date) -> date | None:
    with ui.dialog() as dialog, ui.card():
        ui.label(pytanie).classes('text-subtitle1')
        pole = ui.date_input('Data', value=domyslna.isoformat())
        with ui.row().classes('w-full justify-end'):
            ui.button('Anuluj', on_click=lambda: dialog.submit(None)).props('flat')
            ui.button('Zapisz', on_click=lambda: dialog.submit(pole.value))
    wynik = await dialog
    dialog.delete()
    try:
        data = date.fromisoformat(wynik) if wynik else None
    except ValueError:
        data = None
    if data and data > date.today():
        ui.notify('Data nie może być z przyszłości.', type='warning')
        return None
    return data


def _menu_sprawy(w: Wniosek, stan: dict, katalog: Path, po_zmianie: Callable[[], None]) -> None:
    async def edytuj() -> None:
        with ui.dialog() as dialog, ui.card().classes('w-[34rem]'):
            ui.label(f'Dane wniosku {w.nr}').classes('text-h6')
            temat = ui.textarea('Skrócony opis tematu', value=w.temat).classes('w-full').props('autogrow')
            with ui.grid(columns=2).classes('w-full gap-x-4'):
                wnioskodawca = ui.input('Wnioskodawca', value=w.wnioskodawca)
                kontakt = ui.input('E-mail / adres do odpowiedzi', value=w.kontakt)
                data_wplywu = ui.date_input('Data wpływu', value=w.data_wplywu.isoformat())
                kto = ui.input('Inicjały prowadzącego', value=w.kto)
            ui.label('Numeru wniosku nie można zmienić – od niego zależy folder z dokumentami sprawy.') \
                .classes('text-caption text-grey-7')
            with ui.row().classes('w-full justify-end'):
                ui.button('Anuluj', on_click=lambda: dialog.submit(False)).props('flat')
                ui.button('Zapisz', icon='save', on_click=lambda: dialog.submit(True))
        zapisz = await dialog
        if zapisz:
            try:
                rejestr.aktualizuj(w, temat=temat.value, wnioskodawca=wnioskodawca.value, kontakt=kontakt.value,
                                   data_wplywu=date.fromisoformat(data_wplywu.value), kto=kto.value)
            except ValueError as blad:
                ui.notify(str(blad), type='warning')
            else:
                ui.notify('Zapisano dane wniosku.', type='positive')
                po_zmianie()
        dialog.delete()

    async def kwerenda() -> None:
        with ui.dialog() as dialog, ui.card().classes('w-[30rem]'):
            ui.label('Kwerenda – przedłużenie terminu').classes('text-h6')
            ui.label('Gdy odpowiedź wymaga więcej czasu, termin można wydłużyć najwyżej do 2 miesięcy od złożenia '
                     'wniosku. Wnioskodawcę trzeba o tym zawiadomić (Urzęduś przygotuje zawiadomienie).') \
                .classes('text-caption text-grey-8')
            wlaczona = ui.switch('Kwerenda', value=w.kwerenda)
            nowy_termin = ui.date_input('Nowy termin', value=w.termin.isoformat() if w.kwerenda
                                        else w.termin_maksymalny_kwerendy.isoformat()) \
                .bind_enabled_from(wlaczona, 'value')
            ui.label(f'Dopuszczalnie: od {w.termin_podstawowy + timedelta(days=1):%d.%m.%Y} '
                     f'do {w.termin_maksymalny_kwerendy:%d.%m.%Y}.').classes('text-caption text-grey-7')
            with ui.row().classes('w-full justify-end'):
                ui.button('Anuluj', on_click=lambda: dialog.submit(False)).props('flat')
                ui.button('Zapisz', icon='save', on_click=lambda: dialog.submit(True))
        zapisz = await dialog
        if zapisz:
            try:
                rejestr.ustaw_kwerende(w, wlaczona.value,
                                       date.fromisoformat(nowy_termin.value) if wlaczona.value else None)
            except ValueError as blad:
                ui.notify(str(blad), type='warning', multi_line=True)
            else:
                ui.notify(f'Termin odpowiedzi: {w.termin:%d.%m.%Y}.', type='positive')
                po_zmianie()
        dialog.delete()

    async def usun() -> None:
        liczba = sum(1 for p in katalog.rglob('*') if p.is_file()) if katalog.exists() else 0
        pytanie = (f'Usunąć wniosek {w.nr} „{w.temat}”?' +
                   (f' Trwale usunięte zostaną też dokumenty sprawy ({odmiana(liczba, "plik", "pliki", "plików")}).'
                    if liczba else '') + ' Tej operacji nie można cofnąć.')
        if not await potwierdz(pytanie, 'Usuń wniosek'):
            return
        stan['usunieta'] = True
        rejestr.usun(w)
        await run.io_bound(shutil.rmtree, katalog, True)
        ui.notify(f'Usunięto wniosek {w.nr}.', type='positive')
        ui.navigate.to('/')

    with ui.button(icon='more_vert').props('flat round').tooltip('Więcej'):
        with ui.menu():
            ui.menu_item('Edytuj dane wniosku', on_click=edytuj)
            ui.menu_item('Kwerenda – przedłuż termin', on_click=kwerenda)
            ui.separator()
            ui.menu_item('Usuń wniosek', on_click=usun).classes('text-negative')


# --- strona ----------------------------------------------------------------------

def strona_sprawa(id: str) -> None:
    w = rejestr.pobierz(int(id)) if id.isdigit() else None
    if w is None:
        biezacy().zamknij_sprawe()
        ui.label('Nie ma takiej sprawy.')
        return
    szablon = PROJEKT_ODPOWIEDZI.format(wplyw=f'{w.data_wplywu:%d.%m.%Y}')
    stan = {'projekt': szablon, 'szablon': szablon, 'wykryte': {}, 'ukryte': set(), 'generowanie': False}
    katalog = magazyn.katalog_sprawy(w.nr)
    zapisany = stan_sprawy.wczytaj(katalog)
    zapisano = zapisany.pop('zapisano', None)
    stan.update(zapisany)

    odswiezacze: dict[str, Callable[[], None]] = {}

    def po_zmianie_sprawy() -> None:
        """Status, termin albo dane wniosku się zmieniły – odświeżamy nagłówek i przebieg sprawy."""
        naglowek_sprawy.refresh()
        akcje_sprawy.refresh()
        if 'Wniosek' in odswiezacze:
            odswiezacze['Wniosek']()

    with ui.row().classes('w-full items-center justify-between no-wrap'):
        @ui.refreshable
        def naglowek_sprawy() -> None:
            with ui.row().classes('items-center no-wrap'):
                ui.button(icon='arrow_back', on_click=lambda: ui.navigate.to('/')).props('flat round')
                with ui.column().classes('gap-0'):
                    ui.label(f'{w.nr} – {w.temat}').classes('text-h5 text-weight-medium')
                    with ui.row().classes('items-center gap-2 text-grey-7'):
                        ui.label(f'Termin: {w.termin:%d.%m.%Y} ({w.pozostalo})')
                        if w.uwaga_o_terminie:
                            ui.icon('info_outline', size='xs').tooltip(w.uwaga_o_terminie)
                        if w.kwerenda:
                            ui.badge(f'kwerenda +{w.dni_kwerendy} dni', color='purple-1', text_color='purple-9')
                        ui.label(f'· prowadzi {w.kto}')

        naglowek_sprawy()
        with ui.row().classes('items-center gap-3 no-wrap'):
            with ui.row().classes('items-center gap-1 text-caption text-grey-7 no-wrap'):
                ui.icon('cloud_done' if zapisano else 'save', size='xs')
                info_zapisu = ui.label(f'Wczytano zapisaną pracę z {zapisano:%d.%m %H:%M}' if zapisano
                                       else 'Zmiany zapisują się automatycznie')

            @ui.refreshable
            def akcje_sprawy() -> None:
                with ui.row().classes('items-center gap-1 no-wrap'):
                    _przycisk_statusu(w, po_zmianie_sprawy)
                    _menu_sprawy(w, stan, katalog, po_zmianie_sprawy)

            akcje_sprawy()

    # Autozapis: co 2 s porównujemy stan z ostatnio zapisanym – zapisujemy tylko, gdy coś się zmieniło.
    ostatni_zapis = {'json': stan_sprawy.serializuj(stan)}

    def autozapis() -> None:
        if stan.get('usunieta'):  # po usunięciu wniosku nie odtwarzamy jego katalogu
            return
        aktualny = stan_sprawy.serializuj(stan)
        if aktualny == ostatni_zapis['json']:
            return
        try:
            stan_sprawy.zapisz(katalog, stan)
        except OSError as blad:
            if not info_zapisu.is_deleted:
                info_zapisu.set_text(f'Nie udało się zapisać: {blad.strerror}')
            return
        ostatni_zapis['json'] = aktualny
        if not info_zapisu.is_deleted:  # przy wyjściu ze sprawy widok już nie istnieje
            info_zapisu.set_text(f'Zapisano {datetime.now():%H:%M:%S}')

    ui.timer(2.0, autozapis)

    kroki = [
        ('Wniosek', 'description', lambda: _krok_wniosek(w)),
        ('Podobne sprawy', 'manage_search', _krok_podobne),
        ('Wydziały', 'account_tree', lambda: _krok_wydzialy(w)),
        ('Odpowiedzi wydziałów', 'upload_file', lambda: _krok_odpowiedzi(w, po_zmianie_sprawy)),
        ('Projekt odpowiedzi', 'edit_note', lambda: _krok_projekt(w, stan)),
        ('Anonimizacja', 'visibility_off', lambda: _krok_anonimizacja(stan)),
        ('Eksport', 'download', lambda: _krok_eksport(w, stan, po_zmianie_sprawy)),
    ]
    with ui.stepper().props('header-nav alternative-labels flat bordered').classes('w-full') as stepper:
        for i, (nazwa, ikona, budowniczy) in enumerate(kroki):
            with ui.step(nazwa, icon=ikona):
                if odswiez := budowniczy():
                    odswiezacze[nazwa] = odswiez
                with ui.stepper_navigation():
                    if i < len(kroki) - 1:
                        ui.button('Dalej', on_click=stepper.next)
                    if i > 0:
                        ui.button('Wstecz', on_click=stepper.previous).props('flat')
    # Kroki zależne od treści projektu odświeżamy przy wejściu (projekt mógł się zmienić).
    stepper.on_value_change(lambda e: odswiezacze[e.value]() if e.value in odswiezacze else None)
    # Urzęduś pracuje na tej sprawie i po zatwierdzeniu zmian z czatu odświeża te kroki.
    def przy_zamknieciu() -> None:
        stan['generowanie'] = False  # przerywa pisanie pisma przez Bielika – nikt go już nie zobaczy
        autozapis()

    biezacy().otworz_sprawe(w, stan, list(odswiezacze.values()), przy_zamknieciu=przy_zamknieciu)
