"""Panel anonimizacji: tekst z proponowanymi danymi osobowymi do zaczernienia (szare → czarne po kliknięciu).

Wspólny dla kroku „Anonimizacja” w sprawie (projekt pisma) i ekranu „Anonimizacja pliku” (dowolny dokument).
Stan w słowniku: `stan[klucz_tekstu]` – tekst, `stan['wykryte']` – {ciąg: typ}, `stan['ukryte']` – zatwierdzone.
"""

from collections.abc import Callable

from nicegui import ui

from .. import dziennik
from ..ai import BladAI
from ..anonimizacja import podziel_na_fragmenty, wykryj_wzorce
from ..uslugi import bielik
from .komponenty import blad_ai, odmiana, wskaznik_postepu

RECZNE = 'Dodane ręcznie'


class PanelAnonimizacji:
    def __init__(self, stan: dict, *, klucz_tekstu: str, pusty: str = 'Brak tekstu do sprawdzenia.',
                 po_zmianie: Callable[[], None] | None = None, sprawa: str = '') -> None:
        self.stan = stan
        self.klucz = klucz_tekstu
        self.sprawa = sprawa  # numer sprawy do dziennika AI ('' – plik spoza rejestru)
        self.pusty = pusty
        self.po_zmianie = po_zmianie or (lambda: None)
        self._zbuduj()

    @property
    def tekst(self) -> str:
        return self.stan.get(self.klucz) or ''

    # --- czynności

    async def wykryj(self, *, uzyj_ai: bool = True) -> None:
        """Najpierw wzorce (od razu), potem Bielik – jego propozycje dochodzą, gdy model odpowie."""
        # Komunikaty pokazujemy w kontekście panelu – wywołujący element (np. pole wgrywania) mógł już zniknąć.
        tekst = self.tekst
        if not tekst.strip():
            with self.info:
                ui.notify(self.pusty, type='warning')
            return
        reczne = {c: t for c, t in self.stan['wykryte'].items() if t == RECZNE}
        self.stan['wykryte'] = {**wykryj_wzorce(tekst), **reczne}
        wzorce = len(self.stan['wykryte']) - len(reczne)
        bielik_odpowiedzial = False
        self.odswiez()
        if uzyj_ai:
            self.przycisk.props('loading')
            self.postep.set_visibility(True)
            try:
                for ciag in await bielik.wykryj_dane_osobowe(tekst):
                    self.stan['wykryte'].setdefault(ciag, 'Dane osobowe (Bielik)')
                bielik_odpowiedzial = True
            except BladAI as blad:
                if not self.info.is_deleted:
                    with self.info:
                        blad_ai(f'Bielik niedostępny – pokazuję dane wykryte bez AI (imiona i nazwiska, adresy, '
                                f'PESEL, telefony, e-maile…). {blad}')
            finally:
                if not self.przycisk.is_deleted:
                    self.przycisk.props(remove='loading')
                    self.postep.set_visibility(False)
            if self.przycisk.is_deleted:
                return
            self.odswiez()
        n = len(self.stan['wykryte'])
        dziennik.zapisz('Propozycje danych osobowych do ukrycia',
                        kto=dziennik.AI if bielik_odpowiedzial else dziennik.ASYSTENT, sprawa=self.sprawa,
                        szczegoly=f'wzorce: {wzorce}, Bielik: '
                                  f'{n - wzorce - len(reczne) if bielik_odpowiedzial else "niedostępny"}')
        with self.info:
            ui.notify(f'Znaleziono {odmiana(n, "fragment", "fragmenty", "fragmentów")} do sprawdzenia.')

    def przelacz(self, ciag: str) -> None:
        self.stan['ukryte'] ^= {ciag}
        self.odswiez()

    def zatwierdz_wszystkie(self) -> None:
        self.stan['ukryte'] |= set(self.stan['wykryte'])
        self.odswiez()

    def dodaj_recznie(self) -> None:
        ciag = (self.reczny.value or '').strip()
        if not ciag or ciag not in self.tekst:
            ui.notify('Nie ma takiego fragmentu w tekście – przepisz go dokładnie.', type='warning')
            return
        self.stan['wykryte'][ciag] = RECZNE
        self.stan['ukryte'].add(ciag)
        self.reczny.value = ''
        self.odswiez()

    def odswiez(self) -> None:
        self.widok.refresh()
        self.po_zmianie()

    # --- widok

    def _zbuduj(self) -> None:
        with ui.row().classes('w-full no-wrap gap-6 items-start'):
            kontener = ui.column().classes('col')
            with ui.column().classes('w-72 shrink-0'):
                self.info = ui.label().classes('text-weight-medium')
                ui.label('Szare – propozycja asystenta. Czarne – zatwierdzone do ukrycia. '
                         'Kliknij fragment, żeby przełączyć. Ukrywane są wszystkie wystąpienia.') \
                    .classes('text-caption text-grey-7')
                self.przycisk = ui.button('Wykryj dane osobowe', icon='auto_awesome',
                                          on_click=lambda: self.wykryj()).classes('w-full')
                self.postep = wskaznik_postepu('Bielik szuka danych, których nie złapały wzorce…')
                ui.button('Zatwierdź wszystkie', icon='done_all', on_click=self.zatwierdz_wszystkie) \
                    .props('outline').classes('w-full')
                with ui.row().classes('w-full items-center no-wrap'):
                    self.reczny = ui.input('Ukryj własny fragment').props('dense').classes('col')
                    ui.button(icon='add', on_click=self.dodaj_recznie).props('flat round dense') \
                        .tooltip('Dodaj do ukrycia')

        @ui.refreshable
        def widok() -> None:
            tekst = self.tekst
            obecne = {c for c in self.stan['wykryte'] if c in tekst}
            self.stan['ukryte'] &= obecne
            with ui.card().classes('w-full').props('flat bordered'):
                if not tekst.strip():
                    ui.label(self.pusty).classes('text-grey-7')
                with ui.element('div').classes('text-body1').style('line-height: 2; white-space: pre-wrap'):
                    for fragment, dane in podziel_na_fragmenty(tekst, obecne):
                        if not dane:
                            ui.label(fragment).classes('inline')
                            continue
                        ukryty = fragment in self.stan['ukryte']
                        pole = ui.label(fragment).classes('inline px-1 rounded-borders cursor-pointer ' +
                                                          ('bg-black text-black' if ukryty else 'bg-grey-4'))
                        pole.tooltip(f'{self.stan["wykryte"].get(fragment, "")} – kliknij, żeby '
                                     f'{"odkryć" if ukryty else "ukryć"}')
                        pole.on('click', lambda _, f=fragment: self.przelacz(f))
            self.info.set_text(f'Do ukrycia: {len(self.stan["ukryte"])} z {len(obecne)} wskazanych')

        self.widok = widok
        with kontener:
            widok()
