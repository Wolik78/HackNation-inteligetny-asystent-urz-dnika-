"""Ustawienia aplikacji."""

from nicegui import ui

from ...konfiguracja import KATALOG_DANYCH, LLM_LIMIT_ZNAKOW, TERMIN_DNI, TERMIN_KWERENDA
from ...uslugi import bielik
from ..komponenty import naglowek_strony, otworz_w_systemie, todo


def strona_ustawienia() -> None:
    naglowek_strony('Ustawienia')
    with ui.card().classes('w-[40rem]').props('flat bordered'):
        ui.label('Model AI (lokalny)').classes('text-subtitle1 text-weight-medium')
        with ui.grid(columns=2).classes('gap-x-6 gap-y-1'):
            for etykieta, wartosc in [('Model', bielik.model), ('Adres serwera', bielik.url),
                                      ('Tekst w jednym zapytaniu', f'do {LLM_LIMIT_ZNAKOW} znaków'),
                                      ('Temperatura', str(bielik.temperatura))]:
                ui.label(etykieta).classes('text-grey-7')
                ui.label(wartosc)
        ui.label('Zmiana: zmienne środowiskowe UDIP_LLM_URL, UDIP_LLM_MODEL, UDIP_LLM_LIMIT_ZNAKOW.') \
            .classes('text-caption text-grey-6')

        async def sprawdz() -> None:
            status = await bielik.status()
            ui.notify(status.komunikat, type='positive' if status.dostepny else 'negative', multi_line=True)

        ui.button('Sprawdź połączenie', icon='network_check', on_click=sprawdz).props('outline')

        ui.separator().classes('my-2')
        ui.label('Terminy').classes('text-subtitle1 text-weight-medium')
        with ui.row():
            ui.number('Termin podstawowy (dni)', value=TERMIN_DNI)
            ui.number('Kwerenda (dni)', value=TERMIN_KWERENDA)
        ui.input('Moje inicjały', value='AK')

        ui.separator().classes('my-2')
        ui.label('Dane').classes('text-subtitle1 text-weight-medium')
        ui.label('Wszystkie wgrane dokumenty są przechowywane lokalnie w folderze:').classes('text-grey-8')
        with ui.row().classes('items-center no-wrap'):
            ui.label(str(KATALOG_DANYCH)).classes('text-caption bg-grey-2 q-pa-xs rounded-borders')

            def otworz() -> None:
                KATALOG_DANYCH.mkdir(parents=True, exist_ok=True)
                otworz_w_systemie(KATALOG_DANYCH)

            ui.button('Otwórz', icon='folder_open', on_click=otworz).props('flat dense')

        ui.button('Zapisz', icon='save', on_click=todo('zapis ustawień')).classes('q-mt-md')
