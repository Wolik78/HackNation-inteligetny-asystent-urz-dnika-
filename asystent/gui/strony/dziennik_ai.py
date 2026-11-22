"""Dziennik działań AI: co zaproponował asystent, co zatwierdził urzędnik i kiedy (bez danych osobowych)."""

from nicegui import ui

from ... import dziennik
from ..komponenty import naglowek_strony

KOLUMNY = [
    {'name': 'kiedy', 'label': 'Kiedy', 'field': 'kiedy', 'align': 'left', 'sortable': True},
    {'name': 'kto', 'label': 'Kto', 'field': 'kto', 'align': 'left'},
    {'name': 'czynnosc', 'label': 'Czynność', 'field': 'czynnosc', 'align': 'left'},
    {'name': 'sprawa', 'label': 'Sprawa', 'field': 'sprawa', 'align': 'left'},
    {'name': 'szczegoly', 'label': 'Szczegóły', 'field': 'szczegoly', 'align': 'left'},
]


def strona_dziennik_ai() -> None:
    naglowek_strony('Dziennik działań AI', 'Co zaproponował asystent, co zatwierdził urzędnik i kiedy. '
                                           'Zapisywane są tylko metadane – bez treści dokumentów i danych osobowych.')
    stan = {'sprawa': ''}

    with ui.row().classes('items-center'):
        ui.input('Numer sprawy (filtr)', on_change=lambda e: (stan.update(sprawa=(e.value or '').strip()),
                                                              tabela.refresh())) \
            .props('dense outlined clearable').classes('w-64')
        ui.button('Odśwież', icon='refresh', on_click=lambda: tabela.refresh()).props('flat')

    @ui.refreshable
    def tabela() -> None:
        wpisy = dziennik.wpisy(sprawa=stan['sprawa'] or None)
        if not wpisy:
            ui.label('Brak wpisów.').classes('text-grey-7')
            return
        wiersze = [{'kiedy': w.kiedy.replace('T', ' '), 'kto': w.kto, 'czynnosc': w.czynnosc, 'sprawa': w.sprawa,
                    'szczegoly': w.szczegoly} for w in wpisy]
        ui.table(columns=KOLUMNY, rows=wiersze, pagination=25).classes('w-full').props('flat bordered dense')

    tabela()
