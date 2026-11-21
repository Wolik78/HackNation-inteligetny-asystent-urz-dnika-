"""Widok sprawy: kolejne kroki od wniosku do wysłanej odpowiedzi."""

import shutil
from datetime import date
from pathlib import Path

from nicegui import app, run, ui

from ... import rejestr
from ...pliki import FORMATY, Kategoria, ZapisanyPlik, eksportuj, nazwa_pliku_odpowiedzi
from ...rejestr import Wniosek
from ...uslugi import magazyn
from ..komponenty import (WgranePliki, karta_pliku, naglowek_strony, otworz_w_systemie, strefa_wgrywania,
                          todo, zapisz_wgrane)
from .wnioski import KOLOR_STATUSU

# --- dane testowe (do podmiany przez moduły wyszukiwania i AI) -------------------

PODOBNE_SPRAWY = [
    ('UDIP.112.2025', 'Wydatki na promocję miasta w 2024 r.', 'Biuro Komunikacji Społecznej', '12.03.2025', 92),
    ('UDIP.87.2025', 'Budżet kampanii reklamowych miasta', 'Wydział Finansów', '02.02.2025', 78),
    ('UDIP.240.2024', 'Umowy z agencjami PR', 'Wydział Zamówień Publicznych', '18.10.2024', 64),
]

# TODO: podmienić na listę z https://bip.um.bydgoszcz.pl/artykuly/198/wydzialy i /1158/biura
WYDZIALY = [
    ('Biuro Komunikacji Społecznej', 'w archiwum 3 podobne sprawy obsłużone przez to biuro', 92),
    ('Wydział Finansów', 'pytanie dotyczy kwot wydatków z budżetu', 74),
    ('Wydział Zamówień Publicznych', 'możliwe umowy z wykonawcami', 40),
]

PROJEKT_ODPOWIEDZI = (
    'Szanowny Panie,\n\n'
    'w odpowiedzi na wniosek o udostępnienie informacji publicznej z dnia {wplyw} '
    'uprzejmie informuję, że [TODO: treść wygenerowana na podstawie odpowiedzi wydziałów].\n\n'
    'Podstawa prawna: art. 2 ust. 1 i art. 10 ust. 1 ustawy z dnia 6 września 2001 r. '
    'o dostępie do informacji publicznej.\n\n'
    'Z poważaniem'
)

FRAGMENTY_ANONIMIZACJI = [
    ('Szanowny Panie ', None),
    ('Janie Kowalski', 'Imię i nazwisko'),
    (', zam. ', None),
    ('ul. Długa 5/3, 85-001 Bydgoszcz', 'Adres'),
    (', tel. ', None),
    ('601 234 567', 'Telefon'),
    (', w odpowiedzi na wniosek uprzejmie informuję, że wydatki na promocję miasta w 2025 r. '
     'wyniosły 1 240 000 zł. Umowę z wykonawcą podpisał ', None),
    ('Piotr Nowak', 'Imię i nazwisko (osoba pełniąca funkcję publiczną?)'),
    (', prezes zarządu. Kontakt w sprawie: ', None),
    ('j.kowalski@example.com', 'E-mail'),
    ('.', None),
]


# --- kroki ---------------------------------------------------------------------

def _krok_wniosek(w: Wniosek) -> None:
    with ui.grid(columns=2).classes('gap-x-8 gap-y-1'):
        for etykieta, wartosc in [('Wnioskodawca', w.wnioskodawca), ('Kontakt', w.kontakt or '—'),
                                  ('Data wpływu', f'{w.data_wplywu:%d.%m.%Y}'),
                                  ('Termin', f'{w.termin:%d.%m.%Y}'), ('Prowadzi', w.kto)]:
            ui.label(etykieta).classes('text-grey-7')
            ui.label(wartosc)
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


def _krok_podobne() -> None:
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


def _krok_wydzialy() -> None:
    ui.label('Proponowane wydziały').classes('text-weight-medium')
    for nazwa, powod, pewnosc in WYDZIALY:
        with ui.row().classes('items-center no-wrap'):
            ui.checkbox(nazwa, value=pewnosc > 50)
            ui.label(f'({pewnosc}%) {powod}').classes('text-caption text-grey-7')
    ui.textarea('Treść prośby do wydziałów',
                value='Uprzejmie proszę o przygotowanie informacji w zakresie: [TODO]').classes('w-full')
    with ui.row():
        ui.button('Kopiuj treść', icon='content_copy', on_click=todo('kopiowanie do schowka')).props('outline')
        ui.label('Asystent niczego nie wysyła – prośbę wysyłasz sam.').classes('text-caption text-grey-7 self-center')


def _krok_odpowiedzi(w: Wniosek) -> None:
    ui.label('Odpowiedzi z wydziałów').classes('text-weight-medium')
    with ui.row().classes('w-full items-start no-wrap gap-6'):
        with ui.column().classes('w-[26rem] shrink-0'):
            wydzial = ui.select([n for n, _, _ in WYDZIALY], label='Od którego wydziału? (opcjonalnie)',
                                with_input=True, new_value_mode='add-unique', clearable=True).classes('w-full')
            strefa_wgrywania(lambda pliki: wgraj(pliki), tytul='Przeciągnij tutaj odpowiedzi wydziałów', wiele=True)
        lista = ui.column().classes('col')

    async def wgraj(pliki: WgranePliki) -> None:
        zapis = lambda n, d: magazyn.zapisz(d, n, Kategoria.ODPOWIEDZ_WYDZIALU, sprawa=w.nr, opis=wydzial.value)
        if await zapisz_wgrane(pliki, zapis):
            odpowiedzi.refresh()

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


def _krok_projekt(stan: dict) -> None:
    with ui.row().classes('w-full items-center justify-between'):
        ui.label('Projekt odpowiedzi').classes('text-weight-medium')
        ui.button('Generuj projekt', icon='auto_awesome', on_click=todo('generowanie projektu przez AI'))
    ui.textarea().bind_value(stan, 'projekt').classes('w-full').props('outlined autogrow')
    ui.label('Sprawdź treść merytorycznie – projekt przygotowuje AI, decyzja należy do Ciebie.') \
        .classes('text-caption text-grey-7')


def _krok_anonimizacja() -> None:
    licznik = {'zatwierdzone': 0}
    pola = []

    def odswiez() -> None:
        info.set_text(f'Zatwierdzone: {licznik["zatwierdzone"]}/{len(pola)}')

    def przelacz(pole, wymus: bool | None = None) -> None:
        nowy = (not pole.zatwierdzone) if wymus is None else wymus
        if nowy != pole.zatwierdzone:
            licznik['zatwierdzone'] += 1 if nowy else -1
        pole.zatwierdzone = nowy
        if nowy:
            pole.classes(add='bg-black text-black', remove='bg-grey-4')
        else:
            pole.classes(add='bg-grey-4', remove='bg-black text-black')
        odswiez()

    ui.label('TODO: fragmenty wskaże moduł anonimizacji – poniżej przykład.').classes('text-caption text-grey-7')
    with ui.row().classes('w-full no-wrap gap-6 items-start'):
        with ui.card().classes('col').props('flat bordered'):
            with ui.element('div').classes('text-body1').style('line-height: 2'):
                for tekst, typ in FRAGMENTY_ANONIMIZACJI:
                    if typ is None:
                        ui.label(tekst).classes('inline')
                        continue
                    pole = ui.label(tekst).classes('inline px-1 rounded-borders cursor-pointer bg-grey-4')
                    pole.tooltip(f'Wykryto: {typ}')
                    pole.zatwierdzone = False
                    pole.on('click', lambda _, p=pole: przelacz(p))
                    pola.append(pole)

        with ui.column().classes('w-64 shrink-0'):
            info = ui.label().classes('text-weight-medium')
            ui.label('Szare – propozycja asystenta. Czarne – zatwierdzone. '
                     'Kliknij pole, żeby przełączyć.').classes('text-caption text-grey-7')
            ui.button('Zatwierdź wszystkie', on_click=lambda: [przelacz(p, True) for p in pola]).classes('w-full')
            ui.button('Zaznacz własny fragment', on_click=todo('ręczne zaznaczanie tekstu')) \
                .props('outline').classes('w-full')
    odswiez()


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


def _krok_eksport(w: Wniosek, stan: dict) -> None:
    ui.label('Eksport i zamknięcie sprawy').classes('text-weight-medium')
    ui.label('Eksport bierze tekst z kroku „Projekt odpowiedzi”. Kopia zostaje w dokumentach sprawy.') \
        .classes('text-caption text-grey-7')

    async def zapisz(format: str) -> None:
        if not stan['projekt'].strip():
            ui.notify('Projekt odpowiedzi jest pusty.', type='warning')
            return
        await _zapisz_pismo(w, stan['projekt'], format)
        eksporty.refresh()

    with ui.row():
        ui.button('Zapisz .docx', icon='description', on_click=lambda: zapisz('docx'))
        ui.button('Zapisz .txt', icon='article', on_click=lambda: zapisz('txt')).props('outline')
        ui.button('Otwórz folder sprawy', icon='folder_open', on_click=lambda: otworz_folder()).props('flat')

    def otworz_folder() -> None:
        katalog = magazyn.katalog_sprawy(w.nr)
        katalog.mkdir(parents=True, exist_ok=True)
        otworz_w_systemie(katalog)

    @ui.refreshable
    def eksporty() -> None:
        katalog = magazyn.katalog_eksportu(w.nr)
        pliki = sorted(katalog.glob('*')) if katalog.exists() else []
        for plik in pliki:
            with ui.row().classes('items-center gap-2'):
                ui.icon('task', color='green-7')
                ui.label(plik.name).classes('text-primary cursor-pointer underline') \
                    .on('click', lambda _, p=plik: otworz_w_systemie(p)).tooltip('Otwórz')

    eksporty()
    ui.separator().classes('my-2')
    with ui.row().classes('items-center'):
        ui.date_input('Data udzielenia odpowiedzi', value=date.today().isoformat())
        ui.button('Oznacz jako wysłane', icon='mark_email_read', color='positive',
                  on_click=todo('zmiana statusu na "wysłana"'))


# --- strona ----------------------------------------------------------------------

def strona_sprawa(id: str) -> None:
    w = rejestr.pobierz(int(id)) if id.isdigit() else None
    if w is None:
        ui.label('Nie ma takiej sprawy.')
        return
    stan = {'projekt': PROJEKT_ODPOWIEDZI.format(wplyw=f'{w.data_wplywu:%d.%m.%Y}')}

    with ui.row().classes('w-full items-center justify-between'):
        with ui.row().classes('items-center'):
            ui.button(icon='arrow_back', on_click=lambda: ui.navigate.to('/')).props('flat round')
            naglowek_strony(f'{w.nr} – {w.temat}', f'Termin: {w.termin:%d.%m.%Y} ({w.pozostalo})')
        ui.badge(w.status_opis, color=KOLOR_STATUSU[w.status]).classes('text-body2 q-pa-sm')

    kroki = [
        ('Wniosek', 'description', lambda: _krok_wniosek(w)),
        ('Podobne sprawy', 'manage_search', _krok_podobne),
        ('Wydziały', 'account_tree', _krok_wydzialy),
        ('Odpowiedzi wydziałów', 'upload_file', lambda: _krok_odpowiedzi(w)),
        ('Projekt odpowiedzi', 'edit_note', lambda: _krok_projekt(stan)),
        ('Anonimizacja', 'visibility_off', _krok_anonimizacja),
        ('Eksport', 'download', lambda: _krok_eksport(w, stan)),
    ]
    with ui.stepper().props('header-nav alternative-labels flat bordered').classes('w-full') as stepper:
        for i, (nazwa, ikona, budowniczy) in enumerate(kroki):
            with ui.step(nazwa, icon=ikona):
                budowniczy()
                with ui.stepper_navigation():
                    if i < len(kroki) - 1:
                        ui.button('Dalej', on_click=stepper.next)
                    if i > 0:
                        ui.button('Wstecz', on_click=stepper.previous).props('flat')
