"""Anonimizacja dowolnego pliku (test jury J3): wgraj → sprawdź zaznaczone dane → pobierz plik z czarnymi polami.

Plik wynikowy ma ten sam format co oryginał (PDF, Word, TXT; zdjęcie – PNG). Dane są usuwane z pliku, a nie tylko
zakrywane, i na koniec plik jest odczytywany ponownie (także OCR-em), żeby potwierdzić, że ukrytych danych w nim nie ma.
Wszystko dzieje się lokalnie, w folderze danych aplikacji.
"""

import shutil
from datetime import datetime
from pathlib import Path

from nicegui import app, run, ui

from ...konfiguracja import KATALOG_DANYCH
from ...pliki import BladPliku, wyciagnij_tekst
from ...pliki.anonimizacja_pliku import WynikAnonimizacji, zanonimizuj_plik
from ...pliki.walidacja import bezpieczna_nazwa, sprawdz_plik
from ..anonimizacja_widok import PanelAnonimizacji
from ..komponenty import WgranePliki, naglowek_strony, odmiana, otworz_w_systemie, strefa_wgrywania

KATALOG = KATALOG_DANYCH / 'anonimizacja'


def strona_anonimizacja() -> None:
    naglowek_strony('Anonimizacja pliku', 'Wgraj dokument z danymi osobowymi – asystent wskaże dane, Ty zatwierdzasz, '
                                          'a plik wynikowy ma czarne pola zamiast danych.')
    stan: dict = {'plik': None, 'nazwa': '', 'tekst': '', 'ostrzezenia': [], 'wykryte': {}, 'ukryte': set(),
                  'wynik': None}

    async def wgraj(pliki: WgranePliki) -> None:
        nazwa, dane = pliki[0]
        try:
            sprawdz_plik(nazwa, dane)
        except BladPliku as blad:
            ui.notify(str(blad), type='negative')
            return
        katalog = KATALOG / datetime.now().strftime('%Y%m%d-%H%M%S')
        katalog.mkdir(parents=True, exist_ok=True)
        sciezka = katalog / bezpieczna_nazwa(nazwa)
        sciezka.write_bytes(dane)
        with panel.info:  # nie w polu wgrywania – ono zaraz zniknie, a z nim powiadomienie
            odczyt = ui.notification('Odczytuję plik… (skany i zdjęcia – OCR)', spinner=True, timeout=None)
        try:
            ekstrakcja = await run.io_bound(wyciagnij_tekst, sciezka)
        except BladPliku as blad:
            ui.notify(str(blad), type='negative')
            return
        finally:
            odczyt.dismiss()
        stan.update(plik=sciezka, nazwa=nazwa, tekst=ekstrakcja.tekst, ostrzezenia=ekstrakcja.ostrzezenia,
                    wykryte={}, ukryte=set(), wynik=None)
        plik_widok.refresh()
        wynik_widok.refresh()
        if ekstrakcja.tekst.strip():
            await panel.wykryj()  # od razu: wzorce, potem Bielik

    async def zapisz() -> None:
        if stan['plik'] is None:
            ui.notify('Najpierw wgraj plik.', type='warning')
            return
        if not stan['ukryte'] and not await _potwierdz_bez_ukrycia():
            return
        przycisk_zapisz.props('loading')
        try:
            stan['wynik'] = await run.io_bound(zanonimizuj_plik, stan['plik'], set(stan['ukryte']),
                                               stan['plik'].parent / 'wynik')
        finally:
            przycisk_zapisz.props(remove='loading')
        wynik_widok.refresh()

    async def wyczysc() -> None:
        if stan['plik'] is not None:
            await run.io_bound(shutil.rmtree, stan['plik'].parent, True)
        stan.update(plik=None, nazwa='', tekst='', ostrzezenia=[], wykryte={}, ukryte=set(), wynik=None)
        # komunikat przed odświeżeniem – przycisk „Inny plik”, z którego to wywołano, zaraz zniknie
        ui.notify('Usunięto plik i jego zanonimizowaną kopię z tego komputera.', type='info')
        plik_widok.refresh()
        panel.odswiez()
        wynik_widok.refresh()

    with ui.row().classes('w-full gap-6 items-start no-wrap'):
        with ui.column().classes('w-[24rem] shrink-0 gap-3'):
            @ui.refreshable
            def plik_widok() -> None:
                with ui.card().classes('w-full').props('flat bordered'):
                    ui.label('1. Plik').classes('text-subtitle1 text-weight-medium')
                    if stan['plik'] is None:
                        strefa_wgrywania(wgraj, tytul='Przeciągnij tutaj plik do anonimizacji')
                        ui.label('PDF (także skan), Word, TXT albo zdjęcie. Plik zostaje na tym komputerze.') \
                            .classes('text-caption text-grey-7')
                        return
                    with ui.row().classes('items-center gap-2 no-wrap'):
                        ui.icon('description', color='primary')
                        ui.label(stan['nazwa']).classes('text-weight-medium')
                    for ostrzezenie in stan['ostrzezenia']:
                        ui.label(ostrzezenie).classes('text-caption text-orange-9')
                    with ui.row().classes('gap-1'):
                        ui.button('Inny plik', icon='swap_horiz', on_click=wyczysc).props('flat dense')

            plik_widok()

            with ui.card().classes('w-full').props('flat bordered'):
                ui.label('3. Plik wynikowy').classes('text-subtitle1 text-weight-medium')
                przycisk_zapisz = ui.button('Utwórz zanonimizowany plik', icon='visibility_off', on_click=zapisz) \
                    .classes('w-full')

                @ui.refreshable
                def wynik_widok() -> None:
                    wynik: WynikAnonimizacji | None = stan['wynik']
                    if wynik is None:
                        ui.label('Ten sam format co oryginał: dane pod czarnymi polami są usuwane z pliku, '
                                 'a nie tylko zakrywane.').classes('text-caption text-grey-7')
                        return
                    _podsumowanie(wynik)

                wynik_widok()

        with ui.column().classes('col'):
            ui.label('2. Dane do ukrycia').classes('text-subtitle1 text-weight-medium')
            panel = PanelAnonimizacji(stan, klucz_tekstu='tekst', pusty='Wgraj plik – tu pojawi się jego treść '
                                      'z zaznaczonymi danymi osobowymi.',
                                      po_zmianie=lambda: (stan.update(wynik=None), wynik_widok.refresh()))


async def _potwierdz_bez_ukrycia() -> bool:
    with ui.dialog() as dialog, ui.card():
        ui.label('Nie zaznaczono żadnych danych do ukrycia. Utworzyć kopię bez zmian?')
        with ui.row().classes('w-full justify-end'):
            ui.button('Anuluj', on_click=lambda: dialog.submit(False)).props('flat')
            ui.button('Utwórz', on_click=lambda: dialog.submit(True))
    return bool(await dialog)


def _podsumowanie(wynik: WynikAnonimizacji) -> None:
    if wynik.bezpieczny:
        with ui.row().classes('items-center gap-2 no-wrap text-positive'):
            ui.icon('verified_user')
            ui.label(f'Gotowe – ukryto {odmiana(wynik.zakryte, "miejsce", "miejsca", "miejsc")}. '
                     'Kontrola pliku wynikowego: żadnej z ukrytych danych nie da się już odczytać.')
    for ciag in wynik.nieznalezione:
        ui.label(f'Nie udało się zlokalizować w pliku: „{ciag}” – sprawdź plik wynikowy.') \
            .classes('text-caption text-negative')
    for ciag in wynik.pozostale:
        ui.label(f'Uwaga: w pliku wynikowym nadal widać „{ciag}”.').classes('text-caption text-negative')
    for uwaga in wynik.uwagi:
        ui.label(uwaga).classes('text-caption text-orange-9')
    ui.label(wynik.sciezka.name).classes('text-caption text-grey-8')
    with ui.row().classes('gap-1'):
        ui.button('Zapisz jako…', icon='save_alt', on_click=lambda: _zapisz_jako(wynik.sciezka))
        ui.button('Otwórz', icon='open_in_new', on_click=lambda: otworz_w_systemie(wynik.sciezka)).props('flat')
        ui.button('Folder', icon='folder_open', on_click=lambda: otworz_w_systemie(wynik.sciezka.parent)) \
            .props('flat')


async def _zapisz_jako(sciezka: Path) -> None:
    okno = app.native.main_window
    if okno is None:  # tryb przeglądarki
        ui.download.file(sciezka, sciezka.name)
        return
    import webview  # dostępne tylko w trybie okna
    wybor = await okno.create_file_dialog(webview.FileDialog.SAVE, save_filename=sciezka.name,
                                          file_types=(f'Plik {sciezka.suffix.upper().lstrip(".")} (*{sciezka.suffix})',))
    if not wybor:
        return
    cel = Path(wybor if isinstance(wybor, str) else wybor[0])
    await run.io_bound(shutil.copyfile, sciezka, cel.with_suffix(sciezka.suffix))
    ui.notify(f'Zapisano: {cel.with_suffix(sciezka.suffix)}', type='positive')
