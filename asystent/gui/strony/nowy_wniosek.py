"""Rejestracja nowego wniosku: wgranie pliku, analiza przez Bielika, sprawdzenie danych, zatwierdzenie."""

from datetime import date

from nicegui import run, ui

from ... import klasyfikacja, rejestr
from ...ai import AnalizaWniosku, BladAI, WynikDoboru
from ...ai.wydzialy import dobierz
from ...pliki import Kategoria, ZapisanyPlik
from ...uslugi import bielik, magazyn
from ..komponenty import (WgranePliki, blad_ai, karta_pliku, naglowek_strony, strefa_wgrywania, wskaznik_postepu,
                          zapisz_wgrane)

WYMAGANE = {'Pole wymagane': lambda v: bool(v and str(v).strip())}


def strona_nowy_wniosek() -> None:
    stan: dict = {'plik': None, 'analiza': None, 'wydzialy': None, 'uzasadnienie_rodzaju': ''}

    async def wgraj(pliki: WgranePliki) -> None:
        zapisane = await zapisz_wgrane(pliki[:1], lambda n, d: magazyn.zapisz(d, n, Kategoria.WNIOSEK))
        if zapisane:
            stan['plik'] = zapisane[0]
            podglad.refresh()
            await analizuj(automatycznie=True)

    async def usun_plik(plik: ZapisanyPlik) -> None:
        await run.io_bound(magazyn.usun, plik)
        stan['plik'] = None
        stan['analiza'] = stan['wydzialy'] = None
        podglad.refresh()
        podpowiedz.refresh()

    def zmien_rodzaj() -> None:
        # uzasadnienie dotyczy rodzaju wskazanego przez asystenta – po zmianie przez urzędnika już nie pasuje
        # (przy podpowiedzi asystenta uzasadnienie jest ustawiane zaraz po rodzaju)
        stan['uzasadnienie_rodzaju'] = ''
        podpowiedz.refresh()

    async def analizuj(automatycznie: bool = False) -> None:
        plik: ZapisanyPlik | None = stan['plik']
        if plik is None:
            ui.notify('Najpierw wgraj plik wniosku.', type='warning')
            return
        tekst = plik.tekst()
        if not tekst.strip():
            with przycisk_ai:  # kontekst przycisku – pole wgrywania, z którego przyszło wywołanie, już zniknęło
                ui.notify('W pliku nie ma tekstu do analizy (to może być skan).', type='warning')
            return
        aktualne = lambda: stan['plik'] is plik and not przycisk_ai.is_deleted  # noqa: E731 – plik nie zmieniony

        # 1. od razu, bez modelu: wydziały ze słów kluczowych (lista z BIP) i rodzaj sprawy z reguł
        stan['wydzialy'] = await run.io_bound(dobierz, tekst, uzyj_llm=False)
        rodzaj.value, stan['uzasadnienie_rodzaju'] = klasyfikacja.podpowiedz_regulami(tekst)
        podpowiedz.refresh()

        przycisk_ai.props('loading')
        postep.opis.set_text('Bielik analizuje wniosek… zwykle 30–60 s, możesz w tym czasie wypełniać pola.')
        postep.set_visibility(True)
        try:
            # 2. skrócony opis i kwerenda
            try:
                analiza = await bielik.analizuj_wniosek(tekst)
            except BladAI as blad:
                if aktualne():
                    with przycisk_ai:
                        blad_ai(f'Analiza AI niedostępna – uzupełnij pola ręcznie. {blad}' if automatycznie
                                else str(blad))
                return
            if not aktualne():
                return
            stan['analiza'] = analiza
            if analiza.skrocony_opis and (not automatycznie or not temat.value.strip()):
                temat.value = analiza.skrocony_opis
            kwerenda.value = analiza.czy_wymaga_kwerendy
            rodzaj.value, stan['uzasadnienie_rodzaju'] = klasyfikacja.ustal_rodzaj(
                tekst, analiza.rodzaj, analiza.uzasadnienie_rodzaju)
            podpowiedz.refresh()

            # 3. Bielik wybiera wydziały spośród najlepszych kandydatów z rankingu
            postep.opis.set_text('Bielik dobiera wydziały z listy BIP…')
            dobor = await run.io_bound(dobierz, tekst)
            if not aktualne():
                return
            stan['wydzialy'] = dobor
            podpowiedz.refresh()
        finally:
            if not przycisk_ai.is_deleted:
                przycisk_ai.props(remove='loading')
                postep.set_visibility(False)
        with przycisk_ai:
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
            uwaga_terminu = ui.label().classes('text-caption text-grey-7')
            temat = ui.textarea('Skrócony opis tematu', validation=WYMAGANE).classes('w-full').props('autogrow')
            with ui.row().classes('w-full items-center gap-4 no-wrap'):
                kwerenda = ui.checkbox('Kwerenda (przedłużenie terminu do 2 miesięcy)')
                rodzaj = ui.select({k: r.nazwa for k, r in klasyfikacja.RODZAJE.items()}, value=klasyfikacja.DOMYSLNY,
                                   label='Rodzaj sprawy', on_change=lambda: zmien_rodzaj()).classes('w-72')

            @ui.refreshable
            def podpowiedz() -> None:
                analiza: AnalizaWniosku | None = stan['analiza']
                dobor: WynikDoboru | None = stan['wydzialy']
                wybrany = klasyfikacja.rodzaj(rodzaj.value)
                with ui.row().classes('items-start gap-2 no-wrap'):
                    ui.icon(wybrany.ikona, color=wybrany.kolor).classes('q-mt-xs')
                    with ui.column().classes('gap-0'):
                        ui.label(f'Ścieżka: {wybrany.sciezka}').classes('text-caption')
                        if stan['uzasadnienie_rodzaju'] and rodzaj.value != klasyfikacja.DOMYSLNY:
                            ui.label(f'Dlaczego: {stan["uzasadnienie_rodzaju"]}').classes('text-caption text-grey-7')
                if analiza is None and dobor is None:
                    return
                with ui.card().props('flat').classes('w-full bg-blue-1'):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('auto_awesome', color='primary')
                        ui.label('Podpowiedź asystenta – do weryfikacji').classes('text-weight-medium')
                    if dobor is not None:
                        _propozycje_wydzialow(dobor)
                    if analiza and analiza.czy_wymaga_kwerendy:
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
        koniec, uwaga = rejestr.oblicz_termin(wplyw, kwerenda.value)
        termin.value = koniec.strftime('%d.%m.%Y')
        uwaga_terminu.set_text(uwaga)

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
        dobor: WynikDoboru | None = stan['wydzialy']
        try:
            wniosek = rejestr.dodaj(
                nr=nr.value.strip(), temat=temat.value.strip(), wnioskodawca=wnioskodawca.value.strip(),
                data_wplywu=wplyw, kto=kto.value.strip(), kwerenda=kwerenda.value, kontakt=kontakt.value.strip(),
                sugerowane_wydzialy=dobor.etykiety if dobor else None,
                uzasadnienie_wydzialu=dobor.uzasadnienie if dobor else '',
                rodzaj=rodzaj.value, uzasadnienie_rodzaju=stan['uzasadnienie_rodzaju'],
            )
        except ValueError as blad:
            ui.notify(str(blad), type='negative')
            return
        if stan['plik']:
            await run.io_bound(magazyn.przenies_do_sprawy, stan['plik'], wniosek.nr)
        ui.notify(f'Dodano wniosek {wniosek.nr}.', type='positive')
        ui.navigate.to(f'/sprawa/{wniosek.id}')


def _propozycje_wydzialow(dobor: WynikDoboru) -> None:
    """Lista proponowanych wydziałów: skrót, nazwa i dlaczego."""
    if not dobor.propozycje:
        ui.label(dobor.komunikat or 'Nie dopasowano wydziału – wybierzesz go w sprawie, w kroku „Wydziały”.') \
            .classes('text-caption text-grey-8')
        return
    ui.label(f'Wydziały – {dobor.opis_zrodla}:').classes('text-caption text-grey-7')
    for p in dobor.propozycje:
        with ui.row().classes('items-start gap-2 no-wrap'):
            ui.chip(p.skrot, icon='account_tree').props('dense outline color=primary').classes('shrink-0')
            with ui.column().classes('gap-0'):
                ui.label(p.nazwa).classes('text-body2')
                if p.uzasadnienie:
                    ui.label(p.uzasadnienie).classes('text-caption text-grey-8')
