"""Ustawienia aplikacji."""

from nicegui import ui

from ...konfiguracja import KATALOG_DANYCH, TERMIN_DNI, TERMIN_KWERENDA
from ..komponenty import naglowek_strony, otworz_w_systemie, todo


def strona_ustawienia() -> None:
    naglowek_strony('Ustawienia')
    with ui.card().classes('w-[40rem]').props('flat bordered'):
        ui.label('Model AI').classes('text-subtitle1 text-weight-medium')
        ui.radio({'lokalny': 'Lokalny – offline (docelowo w urzędzie)',
                  'online': 'Online – tylko na czas hackathonu'}, value='lokalny')
        ui.input('Nazwa / ścieżka modelu', placeholder='np. bielik-11b-v2.3-instruct').classes('w-full')

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
