"""Wyniki wyszukiwania w archiwum – wspólne dla kroku „Podobne sprawy” i ekranu Archiwum."""

from collections.abc import Callable

from nicegui import background_tasks, ui

from ..ai import BladAI
from ..archiwum import RODZAJ_ARCHIWUM, Dokument, Trafienie, WynikWyszukiwania
from ..uslugi import archiwum


def zaindeksuj_w_tle() -> None:
    """Liczy w tle wektory nowych archiwalnych odpowiedzi – pierwsze wyszukiwanie nie będzie na nie czekać."""
    async def indeksuj() -> None:
        try:
            await archiwum.zaindeksuj()
        except BladAI:
            pass  # LM Studio wyłączone – wektory policzą się przy wyszukiwaniu (do tego czasu szukamy po słowach)
    background_tasks.create(indeksuj(), name='indeks archiwum')


def kolor_trafnosci(procent: int) -> str:
    return 'positive' if procent >= 60 else 'primary' if procent >= 30 else 'grey-6'


def podglad_dokumentu(dokument: Dokument) -> None:
    """Okno z pełną treścią archiwalnej odpowiedzi albo wniosku z rejestru."""
    with ui.dialog() as dialog, ui.card().classes('w-[52rem] max-w-full'):
        with ui.row().classes('w-full items-center justify-between no-wrap'):
            with ui.column().classes('gap-0'):
                ui.label(dokument.tytul).classes('text-subtitle1 text-weight-medium')
                ui.label(_metryka(dokument)).classes('text-caption text-grey-7')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense')
        ui.separator()
        with ui.scroll_area().classes('w-full h-[60vh]'):
            ui.label(dokument.tekst).classes('whitespace-pre-wrap text-body2')
    dialog.open()


def _metryka(dokument: Dokument) -> str:
    czesci = [dokument.opis_rodzaju, dokument.nr, f'{dokument.data:%d.%m.%Y}' if dokument.data else '']
    return ' · '.join(c for c in czesci if c)


def karta_trafienia(trafienie: Trafienie, *, na_wzor: Callable[[Trafienie], None] | None = None,
                    wybrany_wzor: str | None = None) -> None:
    """Jedna podobna sprawa: tytuł, rodzaj, numer, data, trafność, wspólne słowa i przyciski."""
    d = trafienie.dokument
    with ui.card().classes('w-full').props('flat bordered'):
        with ui.row().classes('w-full items-start justify-between no-wrap gap-4'):
            with ui.column().classes('gap-1 col'):
                with ui.row().classes('items-center gap-2 no-wrap'):
                    ui.icon('inventory_2' if d.rodzaj == RODZAJ_ARCHIWUM else 'description', color='grey-7')
                    ui.label(d.tytul).classes('text-weight-medium')
                ui.label(_metryka(d)).classes('text-caption text-grey-7')
                if trafienie.fragment:
                    ui.label(trafienie.fragment).classes('text-caption text-grey-8')
                if trafienie.wspolne_slowa:
                    with ui.row().classes('gap-1 items-center'):
                        ui.label('Wspólne:').classes('text-caption text-grey-7')
                        for slowo in trafienie.wspolne_slowa:
                            ui.badge(slowo, color='blue-1', text_color='blue-9').props('rounded')
            with ui.column().classes('items-end gap-1 shrink-0'):
                with ui.row().classes('items-center no-wrap gap-2'):
                    pasek = ui.linear_progress(trafienie.procent / 100, show_value=False,
                                               color=kolor_trafnosci(trafienie.procent))
                    pasek.classes('w-28').props('rounded size=8px')
                    ui.label(f'{trafienie.procent}%').classes('text-weight-medium w-10 text-right')
                with ui.row().classes('gap-1 no-wrap'):
                    ui.button('Podgląd', icon='visibility', on_click=lambda: podglad_dokumentu(d)).props('flat dense')
                    if d.rodzaj == RODZAJ_ARCHIWUM and na_wzor is not None:
                        if d.plik is not None and d.plik.plik == wybrany_wzor:
                            ui.chip('Wzór pisma', icon='check', color='positive', text_color='white').props('dense')
                        else:
                            ui.button('Użyj jako wzoru', icon='content_paste_go',
                                      on_click=lambda: na_wzor(trafienie)).props('flat dense')
                    if d.wniosek_id is not None:
                        ui.button('Otwórz', icon='open_in_new',
                                  on_click=lambda: ui.navigate.to(f'/sprawa/{d.wniosek_id}')).props('flat dense')


def opis_trybu(wynik: WynikWyszukiwania) -> str:
    rodzaj = 'słowa i znaczenie (model embeddingów)' if wynik.tryb == 'hybryda' else 'wspólne słowa'
    return f'Przeszukano {wynik.liczba_dokumentow} dokumentów · dopasowanie: {rodzaj}.'
