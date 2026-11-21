"""Elementy interfejsu używane na wielu ekranach."""

import html
import logging
import os
import subprocess
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

from nicegui import events, run, ui

from ..konfiguracja import DOZWOLONE_ROZSZERZENIA, MAKS_ROZMIAR_PLIKU
from ..pliki import BladPliku, ZapisanyPlik

log = logging.getLogger(__name__)

WgranePliki = list[tuple[str, bytes]]  # (nazwa, zawartość)
LIMIT_PODGLADU_TEKSTU = 20_000

IKONY_TYPOW = {'PDF': ('picture_as_pdf', 'red-7'), 'DOCX': ('description', 'blue-8'),
               'DOC': ('description', 'blue-8'), 'TXT': ('article', 'grey-7')}


def todo(co: str) -> Callable[[], None]:
    return lambda: ui.notify(f'TODO: {co}', type='info')


def odmiana(n: int, jeden: str, kilka: str, wiele: str) -> str:
    """Polska odmiana liczebnika: 1 plik, 2 pliki, 5 plików."""
    if n == 1:
        return f'{n} {jeden}'
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f'{n} {kilka}'
    return f'{n} {wiele}'


def naglowek_strony(tytul: str, podtytul: str = '') -> None:
    with ui.column().classes('gap-0 mb-2'):
        ui.label(tytul).classes('text-h5 text-weight-medium')
        if podtytul:
            ui.label(podtytul).classes('text-grey-7')


def kafelek(liczba: int, opis: str, kolor: str) -> None:
    with ui.card().classes('w-48').props('flat bordered'):
        ui.label(str(liczba)).classes(f'text-h4 text-weight-medium text-{kolor}')
        ui.label(opis).classes('text-grey-7')


def blad_ai(tresc: str) -> None:
    """Komunikat o niedostępnym lub błędnie działającym modelu – zostaje dłużej, bo bywa długi."""
    ui.notify(tresc, type='warning', multi_line=True, timeout=12_000, close_button='OK')


def wskaznik_postepu(tekst: str) -> ui.row:
    """Ukryty wiersz „spinner + opis” do pokazywania w trakcie pracy modelu."""
    with ui.row().classes('items-center gap-2 text-primary') as wiersz:
        ui.spinner(size='sm')
        ui.label(tekst).classes('text-caption')
    wiersz.set_visibility(False)
    return wiersz


def otworz_w_systemie(sciezka: Path) -> None:
    """Otwiera plik lub folder w domyślnym programie (aplikacja działa lokalnie)."""
    if sys.platform == 'win32':
        os.startfile(sciezka)  # noqa: S606 – lokalny plik wgrany przez urzędnika
    else:
        subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', str(sciezka)], check=False)


async def potwierdz(pytanie: str, przycisk: str = 'Usuń') -> bool:
    with ui.dialog() as dialog, ui.card():
        ui.label(pytanie)
        with ui.row().classes('w-full justify-end'):
            ui.button('Anuluj', on_click=lambda: dialog.submit(False)).props('flat')
            ui.button(przycisk, color='negative', on_click=lambda: dialog.submit(True))
    wynik = await dialog
    dialog.delete()
    return bool(wynik)


# --- wgrywanie plików ----------------------------------------------------------

_SZABLON_STREFY = '''
<div class="relative-position column items-center justify-center q-pa-lg full-width text-center"
     style="min-height: 150px">
  <q-spinner v-if="props.isUploading" color="primary" size="44px" />
  <q-icon v-else name="upload_file" size="44px" color="primary" />
  <div class="text-subtitle1 text-weight-medium q-mt-sm text-grey-9">{tytul}</div>
  <div class="text-caption text-grey-7">albo kliknij, żeby wybrać z dysku · {typy} · do {limit} MB</div>
  <q-uploader-add-trigger />
</div>
'''


def strefa_wgrywania(obsluga: Callable[[WgranePliki], Awaitable[None]], *,
                     tytul: str = 'Przeciągnij plik tutaj', wiele: bool = False) -> ui.upload:
    """Duże pole „przeciągnij i upuść” – plik wgrywa się od razu po upuszczeniu."""
    typy = ', '.join(r.lstrip('.').upper() for r in DOZWOLONE_ROZSZERZENIA)
    limit_mb = MAKS_ROZMIAR_PLIKU // 1024 // 1024

    # Czyścimy pole przed obsługą – obsługa (np. analiza AI) może potrwać albo usunąć samo pole z ekranu.
    async def jeden(e: events.UploadEventArguments) -> None:
        pliki = [(e.file.name, await e.file.read())]
        upload.reset()
        await obsluga(pliki)

    async def wiele_naraz(e: events.MultiUploadEventArguments) -> None:
        pliki = [(f.name, await f.read()) for f in e.files]
        upload.reset()
        await obsluga(pliki)

    upload = ui.upload(
        multiple=wiele, auto_upload=True, max_file_size=MAKS_ROZMIAR_PLIKU,
        on_upload=None if wiele else jeden,
        on_multi_upload=wiele_naraz if wiele else None,
        on_rejected=lambda: ui.notify(f'Plik odrzucony. Dozwolone: {typy}, maksymalnie {limit_mb} MB.',
                                      type='negative'),
    ).props(f'accept="{",".join(DOZWOLONE_ROZSZERZENIA)}" flat color=white text-color=grey-8') \
     .classes('strefa-wgrywania')
    upload.add_slot('header', _SZABLON_STREFY.format(tytul=html.escape(tytul), typy=typy, limit=limit_mb))
    return upload


async def zapisz_wgrane(pliki: WgranePliki, zapis: Callable[[str, bytes], ZapisanyPlik]) -> list[ZapisanyPlik]:
    """Zapisuje wgrane pliki w tle (bez blokowania okna) i pokazuje podsumowanie."""
    zapisane: list[ZapisanyPlik] = []
    bledy: list[str] = []
    postep = ui.notification(spinner=True, timeout=None) if len(pliki) > 1 else None

    for i, (nazwa, dane) in enumerate(pliki, start=1):
        if postep:
            postep.message = f'Przetwarzanie {i} z {len(pliki)}: {nazwa}'
        try:
            zapisane.append(await run.io_bound(zapis, nazwa, dane))
        except BladPliku as blad:
            bledy.append(f'{nazwa}: {blad}')
        except Exception:
            log.exception('Nie udało się zapisać pliku %s', nazwa)
            bledy.append(f'{nazwa}: nieoczekiwany błąd zapisu.')

    if postep:
        postep.dismiss()
    nowe = [p for p in zapisane if not p.duplikat]
    duplikaty = len(zapisane) - len(nowe)
    if nowe:
        ui.notify(f'Wgrano {odmiana(len(nowe), "plik", "pliki", "plików")}.', type='positive')
    if duplikaty:
        ui.notify(f'{odmiana(duplikaty, "plik był już wgrany", "pliki były już wgrane", "plików było już wgranych")}'
                  ' wcześniej – użyto istniejącej kopii.', type='info')
    for blad in bledy[:3]:  # timeout w ms (przekazywany wprost do Quasara)
        ui.notify(blad, type='negative', multi_line=True, timeout=15_000, close_button='OK')
    if len(bledy) > 3:
        ui.notify(f'…i jeszcze {odmiana(len(bledy) - 3, "błąd", "błędy", "błędów")}.', type='negative')
    return zapisane


# --- wyświetlanie plików --------------------------------------------------------

def _opis_pliku(plik: ZapisanyPlik) -> str:
    czesci = [plik.typ]
    if plik.liczba_stron:
        czesci.append(f'{plik.liczba_stron} str.')
    czesci.append(f'{plik.liczba_znakow:,} znaków'.replace(',', ' '))
    czesci.append(f'{plik.rozmiar / 1024:.0f} KB' if plik.rozmiar < 1024 * 1024
                  else f'{plik.rozmiar / 1024 / 1024:.1f} MB')
    czesci.append(f'dodano {plik.data_dodania:%d.%m.%Y %H:%M}')
    if plik.opis:
        czesci.insert(0, plik.opis)
    return ' · '.join(czesci)


def karta_pliku(plik: ZapisanyPlik, *, on_usun: Callable[[ZapisanyPlik], Awaitable[None] | None] | None = None,
                pokaz_tekst: bool = False) -> None:
    """Karta wgranego pliku: dane, ostrzeżenia, podgląd odczytanego tekstu."""
    ikona, kolor = IKONY_TYPOW.get(plik.typ, ('insert_drive_file', 'grey-7'))

    async def usun() -> None:
        if await potwierdz(f'Usunąć plik „{plik.nazwa_oryginalna}” z aplikacji?'):
            await on_usun(plik)

    with ui.card().props('flat bordered').classes('w-full q-pa-sm'):
        with ui.row().classes('w-full items-center no-wrap'):
            ui.icon(ikona, size='md', color=kolor)
            with ui.column().classes('gap-0 col min-w-0'):
                ui.label(plik.nazwa_oryginalna).classes('text-weight-medium ellipsis full-width')
                ui.label(_opis_pliku(plik)).classes('text-caption text-grey-7')
            ui.button(icon='open_in_new', on_click=lambda: otworz_w_systemie(plik.sciezka)) \
                .props('flat round dense').tooltip('Otwórz w domyślnym programie')
            if on_usun:
                ui.button(icon='delete_outline', on_click=usun) \
                    .props('flat round dense color=negative').tooltip('Usuń z aplikacji')

        for ostrzezenie in plik.ostrzezenia:
            with ui.row().classes('items-center no-wrap gap-1 text-orange-9'):
                ui.icon('warning_amber', size='xs')
                ui.label(ostrzezenie).classes('text-caption')

        rozwin = ui.expansion('Tekst odczytany z pliku', icon='notes', value=pokaz_tekst) \
            .props('dense').classes('w-full text-body2')
        with rozwin:
            kontener = ui.column().classes('w-full')

        def zaladuj_tekst() -> None:  # dopiero przy rozwinięciu – przy setkach plików to ważne
            if kontener.default_slot.children:
                return
            tekst = plik.tekst()
            with kontener:
                with ui.scroll_area().classes('w-full h-64 bg-grey-1 rounded-borders'):
                    ui.label(tekst[:LIMIT_PODGLADU_TEKSTU] or '(brak tekstu)') \
                        .classes('text-body2').style('white-space: pre-wrap')
                if len(tekst) > LIMIT_PODGLADU_TEKSTU:
                    ui.label(f'Pokazano pierwsze {LIMIT_PODGLADU_TEKSTU:,} z {len(tekst):,} znaków.'
                             .replace(',', ' ')).classes('text-caption text-grey-7')

        rozwin.on_value_change(lambda e: e.value and zaladuj_tekst())
        if pokaz_tekst:
            zaladuj_tekst()
