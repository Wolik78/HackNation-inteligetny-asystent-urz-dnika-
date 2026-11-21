"""Archiwum odpowiedzi: wyszukiwarka podobnych spraw w archiwalnych odpowiedziach i rejestrze (J1)."""

from nicegui import ui

from ...archiwum import RODZAJ_ARCHIWUM
from ...uslugi import archiwum
from ..archiwum_widok import karta_trafienia, opis_trybu, podglad_dokumentu
from ..komponenty import naglowek_strony, odmiana

PRZYKLADY = ('wydatki na promocję miasta', 'wycinka drzew w parku', 'dotacje dla stowarzyszeń',
             'mandaty straży miejskiej')


def strona_archiwum() -> None:
    naglowek_strony('Archiwum odpowiedzi', 'Szukaj podobnych spraw – wpisz temat albo fragment wniosku.')
    stan: dict = {'wynik': None, 'trwa': False}

    async def szukaj() -> None:
        if stan['trwa']:
            return
        if not pole.value or not pole.value.strip():
            stan['wynik'] = None
            wyniki.refresh()
            return
        stan['trwa'] = True
        wyniki.refresh()
        try:
            stan['wynik'] = await archiwum.szukaj(pole.value, limit=10)
        finally:
            stan['trwa'] = False
        if not pole.is_deleted:
            wyniki.refresh()

    def przyklad(tekst: str) -> None:
        pole.value = tekst
        ui.timer(0, szukaj, once=True)

    with ui.row().classes('w-full items-center no-wrap'):
        pole = ui.input(placeholder='np. wydatki na promocję miasta').classes('col') \
            .props('outlined clearable autofocus').on('keydown.enter', szukaj)
        ui.button('Szukaj', icon='search', on_click=szukaj)
    with ui.row().classes('items-center gap-1'):
        ui.label('Przykłady:').classes('text-caption text-grey-7')
        for tekst in PRZYKLADY:
            ui.button(tekst, on_click=lambda t=tekst: przyklad(t)).props('flat dense no-caps size=sm color=primary')

    @ui.refreshable
    def wyniki() -> None:
        if stan['trwa']:
            with ui.row().classes('items-center gap-2 text-primary'):
                ui.spinner(size='sm')
                ui.label('Szukam… (pierwsze wyszukiwanie po dodaniu dokumentów indeksuje archiwum)') \
                    .classes('text-caption')
            return
        wynik = stan['wynik']
        if wynik is None:
            _zawartosc_archiwum()
            return
        ui.label(opis_trybu(wynik)).classes('text-caption text-grey-7')
        if wynik.komunikat:
            ui.label(wynik.komunikat).classes('text-caption text-orange-9')
        if not wynik.trafienia:
            ui.label('Nic nie znaleziono – spróbuj innych słów.').classes('text-grey-7')
        for trafienie in wynik.trafienia:
            karta_trafienia(trafienie)

    wyniki()


def _zawartosc_archiwum() -> None:
    """Bez zapytania: co jest w archiwum (żeby było widać, że jest na czym szukać)."""
    dokumenty = [d for d in archiwum.dokumenty() if d.rodzaj == RODZAJ_ARCHIWUM]
    if not dokumenty:
        ui.label('Archiwum jest puste. Archiwalne odpowiedzi dodajesz w Bazie wiedzy (rodzaj „Archiwalna '
                 'odpowiedź”) – możesz przeciągnąć cały folder plików naraz.').classes('text-grey-7')
        ui.button('Przejdź do Bazy wiedzy', icon='menu_book', on_click=lambda: ui.navigate.to('/baza')) \
            .props('flat dense')
        return
    ui.label(f'W archiwum: {odmiana(len(dokumenty), "odpowiedź", "odpowiedzi", "odpowiedzi")}. '
             'Wyszukiwanie obejmuje też wnioski z rejestru z ostatniego roku.').classes('text-caption text-grey-7')
    with ui.list().props('bordered separator').classes('w-full'):
        for d in sorted(dokumenty, key=lambda d: d.data or d.plik.data_dodania.date(), reverse=True):
            with ui.item(on_click=lambda d=d: podglad_dokumentu(d)).props('clickable'):
                with ui.item_section().props('avatar'):
                    ui.icon('inventory_2', color='grey-7')
                with ui.item_section():
                    ui.item_label(d.tytul)
                    ui.item_label(' · '.join(c for c in (d.nr, f'{d.data:%d.%m.%Y}' if d.data else '') if c)) \
                        .props('caption')
