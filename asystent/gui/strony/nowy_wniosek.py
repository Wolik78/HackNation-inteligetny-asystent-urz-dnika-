"""Rejestracja nowego wniosku: wgranie pliku, analiza przez Bielika, sprawdzenie danych, zatwierdzenie."""

from datetime import date, timedelta

from nicegui import run, ui

from ... import rejestr
from ...ai import AnalizaWniosku, BladAI
from ...konfiguracja import TERMIN_DNI, TERMIN_KWERENDA
from ...pliki import Kategoria, ZapisanyPlik
from ...uslugi import bielik, magazyn
from ..komponenty import (WgranePliki, blad_ai, karta_pliku, naglowek_strony, strefa_wgrywania, wskaznik_postepu,
                          zapisz_wgrane)

WYMAGANE = {'Pole wymagane': lambda v: bool(v and str(v).strip())}


def strona_nowy_wniosek() -> None:
    stan: dict = {'plik': None, 'analiza': None}

    async def wgraj(pliki: WgranePliki) -> None:
        zapisane = await zapisz_wgrane(pliki[:1], lambda n, d: magazyn.zapisz(d, n, Kategoria.WNIOSEK))
        if zapisane:
            stan['plik'] = zapisane[0]
            podglad.refresh()
            await analizuj(automatycznie=True)

    async def usun_plik(plik: ZapisanyPlik) -> None:
        await run.io_bound(magazyn.usun, plik)
        stan['plik'] = None
        stan['analiza'] = None
        podglad.refresh()
        podpowiedz.refresh()

    async def analizuj(automatycznie: bool = False) -> None:
        plik: ZapisanyPlik | None = stan['plik']
        if plik is None:
            ui.notify('Najpierw wgraj plik wniosku.', type='warning')
            return
        tekst = plik.tekst()
        if not tekst.strip():
            ui.notify('W pliku nie ma tekstu do analizy (to może być skan).', type='warning')
            return

        przycisk_ai.props('loading')
        postep.set_visibility(True)
        try:
            analiza = await bielik.analizuj_wniosek(tekst)
        except BladAI as blad:
            blad_ai(f'Analiza AI niedostępna – uzupełnij pola ręcznie. {blad}' if automatycznie else str(blad))
            return
        finally:
            przycisk_ai.props(remove='loading')
            postep.set_visibility(False)

        stan['analiza'] = analiza
        if analiza.skrocony_opis and (not automatycznie or not temat.value.strip()):
            temat.value = analiza.skrocony_opis
        kwerenda.value = analiza.czy_wymaga_kwerendy
        podpowiedz.refresh()
        ui.notify('Bielik uzupełnił pola – sprawdź je przed zatwierdzeniem.', type='positive')

    naglowek_strony('Nowy wniosek', 'Wgraj plik – Bielik przeanalizuje wniosek. Sprawdź dane i zatwierdź.')

    with ui.row().classes('w-full gap-6 items-start no-wrap'):
        with ui.card().classes('w-[30rem] shrink-0').props('flat bordered'):
            ui.label('1. Plik wniosku').classes('text-subtitle1 text-weight-medium')

            @ui.refreshable
            def podglad() -> None:
                if stan['plik'] is None:
                    strefa_wgrywania(wgraj, tytul='Przeciągnij tutaj plik wniosku')
                    ui.label('Plik i jego analiza zostają na tym komputerze – nic nie jest wysyłane na zewnątrz.') \
                        .classes('text-caption text-grey-7')
                else:
                    karta_pliku(stan['plik'], on_usun=usun_plik, pokaz_tekst=True)
                    ui.button('Wgraj inny plik', icon='swap_horiz', on_click=lambda: usun_plik(stan['plik'])) \
                        .props('flat dense')

            podglad()

        with ui.card().classes('col').props('flat bordered'):
            with ui.row().classes('w-full items-center justify-between'):
                ui.label('2. Dane wniosku').classes('text-subtitle1 text-weight-medium')
                przycisk_ai = ui.button('Analizuj ponownie (Bielik)', icon='auto_awesome',
                                        on_click=lambda: analizuj()).props('flat dense')
            postep = wskaznik_postepu('Bielik analizuje wniosek… zwykle 30–60 s, możesz w tym czasie wypełniać pola.')
            with ui.grid(columns=2).classes('w-full gap-x-4'):
                nr = ui.input('Nr wniosku', value=rejestr.nastepny_numer(), validation=WYMAGANE)
                data_wplywu = ui.date_input('Data wpływu', value=date.today().isoformat())
                wnioskodawca = ui.input('Wnioskodawca', validation=WYMAGANE)
                kontakt = ui.input('E-mail / adres do odpowiedzi')
                kto = ui.input('Inicjały prowadzącego', value='AK')
                termin = ui.input('Termin odpowiedzi').props('readonly')
            temat = ui.textarea('Skrócony opis tematu', validation=WYMAGANE).classes('w-full').props('autogrow')
            kwerenda = ui.checkbox('Kwerenda (przedłużenie terminu do 2 miesięcy)')

            @ui.refreshable
            def podpowiedz() -> None:
                analiza: AnalizaWniosku | None = stan['analiza']
                if analiza is None:
                    return
                with ui.card().props('flat').classes('w-full bg-blue-1'):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('auto_awesome', color='primary')
                        ui.label('Podpowiedź Bielika – do weryfikacji').classes('text-weight-medium')
                    if analiza.sugerowane_wydzialy:
                        with ui.row().classes('gap-1'):
                            for wydzial in analiza.sugerowane_wydzialy:
                                ui.chip(wydzial, icon='account_tree').props('dense outline color=primary')
                    if analiza.uzasadnienie_wydzialu:
                        ui.label(analiza.uzasadnienie_wydzialu).classes('text-caption text-grey-8')
                    if analiza.czy_wymaga_kwerendy:
                        ui.label('Bielik sugeruje kwerendę – zaznaczono pole powyżej.').classes('text-caption text-grey-8')

            podpowiedz()
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
        analiza: AnalizaWniosku | None = stan['analiza']
        try:
            wniosek = rejestr.dodaj(
                nr=nr.value.strip(), temat=temat.value.strip(), wnioskodawca=wnioskodawca.value.strip(),
                data_wplywu=wplyw, kto=kto.value.strip(), kwerenda=kwerenda.value, kontakt=kontakt.value.strip(),
                sugerowane_wydzialy=analiza.sugerowane_wydzialy if analiza else None,
                uzasadnienie_wydzialu=analiza.uzasadnienie_wydzialu if analiza else '',
            )
        except ValueError as blad:
            ui.notify(str(blad), type='negative')
            return
        if stan['plik']:
            await run.io_bound(magazyn.przenies_do_sprawy, stan['plik'], wniosek.nr)
        ui.notify(f'Dodano wniosek {wniosek.nr}.', type='positive')
        ui.navigate.to(f'/sprawa/{wniosek.id}')
