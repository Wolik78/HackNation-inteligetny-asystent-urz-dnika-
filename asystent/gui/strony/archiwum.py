"""Wyszukiwarka w archiwum odpowiedzi (na razie dane przykładowe)."""

from nicegui import ui

from ..komponenty import naglowek_strony, todo

ARCHIWUM = [
    {'nr': 'UDIP.112.2025', 'temat': 'Wydatki na promocję miasta w 2024 r.', 'wydzial': 'Biuro Komunikacji Społecznej', 'data': '12.03.2025', 'podobienstwo': 92},
    {'nr': 'UDIP.87.2025', 'temat': 'Budżet kampanii reklamowych miasta', 'wydzial': 'Wydział Finansów', 'data': '02.02.2025', 'podobienstwo': 78},
    {'nr': 'UDIP.240.2024', 'temat': 'Umowy z agencjami PR', 'wydzial': 'Wydział Zamówień Publicznych', 'data': '18.10.2024', 'podobienstwo': 64},
    {'nr': 'UDIP.15.2025', 'temat': 'Koszt organizacji festiwali', 'wydzial': 'Wydział Kultury', 'data': '20.01.2025', 'podobienstwo': 41},
    {'nr': 'UDIP.301.2024', 'temat': 'Zimowe utrzymanie dróg 2023/24', 'wydzial': 'Wydział Gospodarki Komunalnej', 'data': '05.12.2024', 'podobienstwo': 12},
]

KOLUMNY = [
    {'name': 'nr', 'label': 'Nr', 'field': 'nr', 'align': 'left'},
    {'name': 'temat', 'label': 'Temat', 'field': 'temat', 'align': 'left'},
    {'name': 'wydzial', 'label': 'Wydział', 'field': 'wydzial', 'align': 'left'},
    {'name': 'data', 'label': 'Data odpowiedzi', 'field': 'data', 'align': 'left'},
    {'name': 'podobienstwo', 'label': 'Trafność', 'field': 'podobienstwo', 'align': 'left',
     ':format': 'v => v + "%"'},
]


def strona_archiwum() -> None:
    naglowek_strony('Archiwum odpowiedzi', 'Szukaj podobnych spraw z poprzednich lat.')
    with ui.row().classes('w-full items-center no-wrap'):
        ui.input(placeholder='np. wydatki na promocję miasta').classes('col').props('outlined clearable')
        ui.button('Szukaj', icon='search', on_click=todo('wyszukiwanie w archiwum'))
    ui.label('Archiwalne odpowiedzi dodajesz w Bazie wiedzy. Wyniki poniżej są przykładowe.') \
        .classes('text-caption text-grey-7')
    ui.table(columns=KOLUMNY, rows=ARCHIWUM, row_key='nr', pagination_controls=False) \
        .classes('w-full').props('flat bordered')
