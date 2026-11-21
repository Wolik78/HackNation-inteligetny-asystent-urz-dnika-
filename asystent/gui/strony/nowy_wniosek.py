"""Rejestracja nowego wniosku: wgranie pliku, sprawdzenie danych, zatwierdzenie."""

from datetime import date, timedelta

from nicegui import run, ui

from ... import rejestr
from ...konfiguracja import TERMIN_DNI, TERMIN_KWERENDA
from ...pliki import Kategoria, ZapisanyPlik
from ...uslugi import magazyn
from ..komponenty import WgranePliki, karta_pliku, naglowek_strony, strefa_wgrywania, todo, zapisz_wgrane

WYMAGANE = {'Pole wymagane': lambda v: bool(v and str(v).strip())}


def strona_nowy_wniosek() -> None:
    stan: dict[str, ZapisanyPlik | None] = {'plik': None}

    async def wgraj(pliki: WgranePliki) -> None:
        zapisane = await zapisz_wgrane(pliki[:1], lambda n, d: magazyn.zapisz(d, n, Kategoria.WNIOSEK))
        if zapisane:
            stan['plik'] = zapisane[0]
            podglad.refresh()

    async def usun_plik(plik: ZapisanyPlik) -> None:
        await run.io_bound(magazyn.usun, plik)
        stan['plik'] = None
        podglad.refresh()

    naglowek_strony('Nowy wniosek', 'Wgraj plik, sprawdź dane i zatwierdź – wniosek trafi na listę.')

    with ui.row().classes('w-full gap-6 items-start no-wrap'):
        with ui.card().classes('w-[30rem] shrink-0').props('flat bordered'):
            ui.label('1. Plik wniosku').classes('text-subtitle1 text-weight-medium')

            @ui.refreshable
            def podglad() -> None:
                if stan['plik'] is None:
                    strefa_wgrywania(wgraj, tytul='Przeciągnij tutaj plik wniosku')
                    ui.label('Plik zostaje na tym komputerze – nic nie jest wysyłane na zewnątrz.') \
                        .classes('text-caption text-grey-7')
                else:
                    karta_pliku(stan['plik'], on_usun=usun_plik, pokaz_tekst=True)
                    ui.button('Wgraj inny plik', icon='swap_horiz', on_click=lambda: usun_plik(stan['plik'])) \
                        .props('flat dense')

            podglad()

        with ui.card().classes('col').props('flat bordered'):
            ui.label('2. Dane wniosku').classes('text-subtitle1 text-weight-medium')
            with ui.grid(columns=2).classes('w-full gap-x-4'):
                nr = ui.input('Nr wniosku', value=rejestr.nastepny_numer(), validation=WYMAGANE)
                data_wplywu = ui.date_input('Data wpływu', value=date.today().isoformat())
                wnioskodawca = ui.input('Wnioskodawca', validation=WYMAGANE)
                kontakt = ui.input('E-mail / adres do odpowiedzi')
                kto = ui.input('Inicjały prowadzącego', value='AK')
                termin = ui.input('Termin odpowiedzi').props('readonly')
            temat = ui.textarea('Skrócony opis tematu', validation=WYMAGANE).classes('w-full').props('autogrow')
            kwerenda = ui.checkbox('Kwerenda (przedłużenie terminu do 2 miesięcy)')
            ui.button('Odczytaj dane z pliku', icon='auto_awesome', on_click=todo('AI: wypełnienie pól z treści wniosku')) \
                .props('flat dense')
            with ui.row().classes('w-full justify-end'):
                ui.button('Anuluj', on_click=lambda: anuluj()).props('flat')
                ui.button('Zatwierdź i dodaj do listy', icon='check', on_click=lambda: zatwierdz())

    def przelicz_termin() -> None:
        try:
            wplyw = date.fromisoformat(data_wplywu.value)
        except (TypeError, ValueError):
            termin.value = ''
            return
        termin.value = (wplyw + timedelta(days=TERMIN_KWERENDA if kwerenda.value else TERMIN_DNI)) \
            .strftime('%d.%m.%Y')

    data_wplywu.on_value_change(przelicz_termin)
    kwerenda.on_value_change(przelicz_termin)
    przelicz_termin()

    async def anuluj() -> None:
        if stan['plik']:
            await run.io_bound(magazyn.usun, stan['plik'])
        ui.navigate.to('/')

    async def zatwierdz() -> None:
        if not all([pole.validate() for pole in (nr, wnioskodawca, temat)]):
            ui.notify('Uzupełnij wymagane pola.', type='warning')
            return
        try:
            wplyw = date.fromisoformat(data_wplywu.value)
        except (TypeError, ValueError):
            ui.notify('Podaj poprawną datę wpływu (RRRR-MM-DD).', type='warning')
            return
        try:
            wniosek = rejestr.dodaj(
                nr=nr.value.strip(), temat=temat.value.strip(), wnioskodawca=wnioskodawca.value.strip(),
                data_wplywu=wplyw, kto=kto.value.strip(),
                kwerenda=kwerenda.value, kontakt=kontakt.value.strip(),
            )
        except ValueError as blad:
            ui.notify(str(blad), type='negative')
            return
        if stan['plik']:
            await run.io_bound(magazyn.przenies_do_sprawy, stan['plik'], wniosek.nr)
        ui.notify(f'Dodano wniosek {wniosek.nr}.', type='positive')
        ui.navigate.to(f'/sprawa/{wniosek.id}')
