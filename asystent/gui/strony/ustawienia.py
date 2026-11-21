"""Ustawienia aplikacji."""

from datetime import date

from nicegui import ui

from ... import rejestr
from ...konfiguracja import KATALOG_DANYCH, LLM_LIMIT_ZNAKOW, TERMIN_DNI
from ...terminy import swieta
from ...uslugi import bielik
from ..komponenty import naglowek_strony, otworz_w_systemie, potwierdz


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
        ui.label('Terminy (liczone automatycznie)').classes('text-subtitle1 text-weight-medium')
        for zasada in (f'Odpowiedź: {TERMIN_DNI} dni od dnia wpływu wniosku, bez dnia wpływu (art. 13 ust. 1 UDIP, '
                       'art. 57 § 1 KPA).',
                       'Kwerenda: termin wydłużony najwyżej do 2 miesięcy od złożenia wniosku (art. 13 ust. 2 UDIP).',
                       'Koniec terminu w sobotę, niedzielę lub święto przesuwa się na najbliższy dzień roboczy '
                       '(art. 57 § 4 KPA).'):
            with ui.row().classes('items-start no-wrap gap-2'):
                ui.icon('rule', size='xs', color='primary').classes('q-mt-xs')
                ui.label(zasada).classes('text-body2')
        najblizsze = sorted((d, n) for rok in (date.today().year, date.today().year + 1)
                            for d, n in swieta(rok).items() if d >= date.today())[:4]
        ui.label('Najbliższe święta: ' + ', '.join(f'{d:%d.%m} {n}' for d, n in najblizsze)) \
            .classes('text-caption text-grey-7')

        ui.separator().classes('my-2')
        ui.label('Dane demonstracyjne').classes('text-subtitle1 text-weight-medium')
        ui.label('Odtwarza 10 wniosków testowych z terminami liczonymi od dzisiaj (np. przed pokazem). '
                 'Wnioski dodane przez Ciebie zostają bez zmian.').classes('text-caption text-grey-7')

        async def przywroc() -> None:
            if await potwierdz('Odtworzyć 10 wniosków testowych? Zmiany w obecnych wnioskach testowych przepadną.',
                               'Odtwórz'):
                rejestr.przywroc_dane_testowe()
                ui.notify('Odtworzono wnioski testowe.', type='positive')

        ui.button('Przywróć wnioski testowe', icon='restart_alt', on_click=przywroc).props('outline')

        ui.separator().classes('my-2')
        ui.label('Dane').classes('text-subtitle1 text-weight-medium')
        ui.label('Wszystkie wgrane dokumenty są przechowywane lokalnie w folderze:').classes('text-grey-8')
        with ui.row().classes('items-center no-wrap'):
            ui.label(str(KATALOG_DANYCH)).classes('text-caption bg-grey-2 q-pa-xs rounded-borders')

            def otworz() -> None:
                KATALOG_DANYCH.mkdir(parents=True, exist_ok=True)
                otworz_w_systemie(KATALOG_DANYCH)

            ui.button('Otwórz', icon='folder_open', on_click=otworz).props('flat dense')
