"""Panel czatu Urzęduś (wysuwany z prawej strony okna)."""

from contextlib import aclosing

from nicegui import run, ui

from .. import rejestr
from ..ai import (BladAI, DaneSprawy, Intencja, ODMOWA, OdpowiedzPozaTematem, POWITANIE, Wynik, usun_markdown)
from ..pliki import Kategoria, eksportuj
from ..uslugi import magazyn, urzedus
from .kontekst import KontekstOkna, biezacy

SZYBKIE_AKCJE_SPRAWY = [
    ('Streść wniosek', 'summarize', Intencja.STRESZCZENIE),
    ('Zaproponuj wydziały', 'account_tree', Intencja.WYDZIALY),
    ('Napisz projekt', 'edit_note', Intencja.PROJEKT),
    ('Sprawdź pismo', 'fact_check', Intencja.KONTROLA),
    ('Znajdź dane osobowe', 'visibility_off', Intencja.DANE_OSOBOWE),
    ('Zawiadomienie o przedłużeniu', 'schedule', Intencja.ZAWIADOMIENIE),
]
SZYBKIE_AKCJE_ZAWSZE = [('Co mam na dziś?', 'today', Intencja.TERMINY)]

STYL_URZEDUSIA = 'bg-color=blue-1 text-color=grey-10'
STYL_UZYTKOWNIKA = 'bg-color=primary text-color=white'

NAZWY_PISM = {
    Intencja.PROSBA_DO_WYDZIALU: 'Prosba_do_wydzialu',
    Intencja.ZAWIADOMIENIE: 'Zawiadomienie_o_przedluzeniu',
    Intencja.WEZWANIE: 'Prosba_o_doprecyzowanie',
}


def _dane_sprawy(kontekst: KontekstOkna) -> DaneSprawy | None:
    w = kontekst.wniosek
    if w is None:
        return None
    wniosek = magazyn.lista(Kategoria.WNIOSEK, sprawa=w.nr)
    odpowiedzi = magazyn.lista(Kategoria.ODPOWIEDZ_WYDZIALU, sprawa=w.nr)
    stan = kontekst.stan_sprawy or {}
    projekt = stan.get('projekt', '')
    return DaneSprawy(
        nr=w.nr, temat=w.temat, data_wplywu=w.data_wplywu, termin=w.termin,
        tekst_wniosku=wniosek[0].tekst() if wniosek else '',
        odpowiedzi_wydzialow='\n\n'.join(f'[{p.opis or p.nazwa_oryginalna}]\n{p.tekst()}' for p in odpowiedzi),
        projekt='' if projekt == stan.get('szablon') else projekt,
        sugerowane_wydzialy=list(w.sugerowane_wydzialy),
        ukryte=set(stan.get('ukryte', ())),
    )


def panel_czatu(zamknij) -> None:
    kontekst = biezacy()
    historia: list[str] = []
    stan = {'zajety': False}

    # --- nagłówek i kontekst ---
    with ui.row().classes('w-full items-center no-wrap'):
        ui.icon('smart_toy', size='md', color='primary')
        with ui.column().classes('gap-0 col'):
            ui.label('Urzęduś').classes('text-subtitle1 text-weight-medium')
            ui.label('asystent AI · działa lokalnie').classes('text-caption text-grey-7')
        ui.button(icon='close', on_click=zamknij).props('flat round dense').tooltip('Zamknij czat')

    @ui.refreshable
    def pasek_kontekstu() -> None:
        w = kontekst.wniosek
        with ui.row().classes('w-full items-center gap-1 text-caption ' + ('text-primary' if w else 'text-grey-7')):
            ui.icon('folder_open' if w else 'info', size='xs')
            ui.label(f'Pracuję na sprawie {w.nr} – {w.temat}' if w
                     else 'Otwórz sprawę, żebym mógł pracować na jej dokumentach.').classes('ellipsis col')
        with ui.row().classes('w-full gap-1'):
            akcje = (SZYBKIE_AKCJE_SPRAWY if w else []) + SZYBKIE_AKCJE_ZAWSZE
            for opis, ikona, intencja in akcje:
                ui.button(opis, icon=ikona, on_click=lambda o=opis, i=intencja: wyslij(o, intencja=i)) \
                    .props('outline rounded dense no-caps size=sm color=primary')

    pasek_kontekstu()
    kontekst.po_zmianie_sprawy(pasek_kontekstu.refresh)

    # --- wiadomości ---
    obszar = ui.scroll_area().classes('w-full col bg-grey-1 rounded-borders')
    with obszar:
        wiadomosci = ui.column().classes('w-full gap-0 q-pa-xs')

    def przewin() -> None:
        ui.timer(0.05, lambda: obszar.scroll_to(percent=1.0), once=True)

    def dodaj(tekst: str, *, od_uzytkownika: bool) -> None:
        with wiadomosci:
            with ui.chat_message(name=None if od_uzytkownika else 'Urzęduś', sent=od_uzytkownika) \
                    .props(STYL_UZYTKOWNIKA if od_uzytkownika else STYL_URZEDUSIA).classes('w-full'):
                ui.label(tekst).style('white-space: pre-wrap')
        przewin()

    # --- pole wpisywania ---
    with ui.row().classes('w-full items-end no-wrap'):
        pole = ui.textarea(placeholder='Napisz do Urzędusia…').props('outlined dense autogrow rows=1') \
            .classes('col')
        przycisk = ui.button(icon='send', on_click=lambda: wyslij()).props('round color=primary')
    pole.on('keydown.enter.exact.prevent', lambda: wyslij())
    ui.label('Urzęduś zajmuje się tylko wnioskami UDIP. Sprawdzaj jego odpowiedzi – decyzja należy do Ciebie.') \
        .classes('text-caption text-grey-6')

    # --- logika ---

    async def wyslij(opis: str | None = None, *, intencja: Intencja | None = None) -> None:
        if stan['zajety']:
            ui.notify('Poczekaj, aż Urzęduś skończy odpowiadać.', type='info')
            return
        tresc = (pole.value or '').strip() if intencja is None else ''
        if intencja is None and not tresc:
            return
        pole.value = ''
        dodaj(opis or tresc, od_uzytkownika=True)

        stan['zajety'] = True
        przycisk.props('loading')
        with wiadomosci:
            with ui.chat_message(name='Urzęduś').props(STYL_URZEDUSIA).classes('w-full'):
                with ui.column().classes('gap-1') as tresc_odp:
                    etykieta = ui.label('').style('white-space: pre-wrap')
                    with ui.row().classes('items-center gap-2') as mysli:  # widoczne do końca odpowiedzi
                        ui.spinner(size='sm')
                        ui.label('Urzęduś myśli…').classes('text-caption text-grey-7')
        przewin()

        odpowiedz = ''
        wynik: Wynik | None = None
        sprawa_w_chwili_pytania = kontekst.wniosek
        try:
            wynik = await urzedus.obsluz(tresc, _dane_sprawy(kontekst), '\n'.join(historia[-4:]), intencja)
            if wynik.strumien is not None:
                async with aclosing(wynik.strumien) as strumien:
                    async for kawalek in strumien:
                        odpowiedz += kawalek
                        etykieta.set_text(odpowiedz)
                        przewin()
                odpowiedz = usun_markdown(odpowiedz)
            else:
                odpowiedz = wynik.tekst
        except OdpowiedzPozaTematem:
            odpowiedz, wynik = ODMOWA, None
        except BladAI as blad:
            odpowiedz, wynik = f'Nie mogę teraz odpowiedzieć. {blad}', None
        finally:
            mysli.set_visibility(False)
            etykieta.set_text(odpowiedz)
            stan['zajety'] = False
            przycisk.props(remove='loading')

        if wynik is not None:
            with tresc_odp:
                _przyciski_akcji(wynik, odpowiedz, kontekst, sprawa_w_chwili_pytania)
        historia.append(f'Urzędnik: {opis or tresc}')
        historia.append(f'Urzęduś: {odpowiedz[:300]}')
        przewin()

    dodaj(POWITANIE, od_uzytkownika=False)


def _przyciski_akcji(wynik: Wynik, odpowiedz: str, kontekst: KontekstOkna, wniosek: rejestr.Wniosek | None) -> None:
    """Przyciski pod odpowiedzią. Nic nie dzieje się bez kliknięcia urzędnika."""

    def ta_sama_sprawa() -> bool:
        if wniosek is None or kontekst.wniosek is None or kontekst.wniosek.id != wniosek.id:
            ui.notify(f'Otwórz sprawę {wniosek.nr if wniosek else ""}, żeby zastosować tę zmianę.', type='warning')
            return False
        return True

    async def kopiuj() -> None:
        await ui.clipboard.write(odpowiedz)
        ui.notify('Skopiowano do schowka.', type='positive')

    def wstaw_projekt() -> None:
        if ta_sama_sprawa() and kontekst.stan_sprawy is not None:
            kontekst.stan_sprawy.update(projekt=odpowiedz, wykryte={}, ukryte=set())
            kontekst.odswiez_widok_sprawy()
            ui.notify('Wstawiono do kroku „Projekt odpowiedzi”. Sprawdź treść przed eksportem.', type='positive')

    def zapisz_wydzialy() -> None:
        if ta_sama_sprawa() and wynik.wydzialy:
            wniosek.sugerowane_wydzialy = wynik.wydzialy.etykiety
            wniosek.uzasadnienie_wydzialu = wynik.wydzialy.uzasadnienie
            rejestr.zapisz_zmiany()
            kontekst.odswiez_widok_sprawy()
            ui.notify('Zapisano wydziały w sprawie.', type='positive')

    def oznacz_dane() -> None:
        if ta_sama_sprawa() and kontekst.stan_sprawy is not None:
            kontekst.stan_sprawy['wykryte'].update({c: 'Dane osobowe (Urzęduś)' for c in wynik.dane_osobowe})
            kontekst.odswiez_widok_sprawy()
            ui.notify('Oznaczono w kroku „Anonimizacja” – zatwierdź tam, co ukryć.', type='positive')

    async def zapisz_pismo() -> None:
        if not ta_sama_sprawa():
            return
        nazwa = f'{NAZWY_PISM[wynik.intencja]}_{wniosek.nr}.docx'
        sciezka = await run.io_bound(eksportuj, odpowiedz, magazyn.katalog_eksportu(wniosek.nr) / nazwa)
        ui.notify(f'Zapisano w dokumentach sprawy: {sciezka.name}', type='positive')

    styl = 'flat dense no-caps size=sm color=primary'
    with ui.row().classes('gap-1'):
        match wynik.intencja:
            case Intencja.PROJEKT if odpowiedz:
                ui.button('Wstaw do projektu', icon='input', on_click=wstaw_projekt).props(styl)
            case Intencja.WYDZIALY if wynik.wydzialy:
                ui.button('Zapisz w sprawie', icon='save', on_click=zapisz_wydzialy).props(styl)
            case Intencja.DANE_OSOBOWE if wynik.dane_osobowe and wynik.zrodlo_danych_osobowych == 'projekt':
                ui.button('Oznacz w anonimizacji', icon='visibility_off', on_click=oznacz_dane).props(styl)
            case Intencja.PROSBA_DO_WYDZIALU | Intencja.ZAWIADOMIENIE | Intencja.WEZWANIE if odpowiedz:
                ui.button('Zapisz .docx w sprawie', icon='description', on_click=zapisz_pismo).props(styl)
            case Intencja.TERMINY:
                for w in wynik.terminy[:5]:
                    ui.button(f'Otwórz {w.nr}', icon='open_in_new',
                              on_click=lambda id=w.id: ui.navigate.to(f'/sprawa/{id}')).props(styl)
        if odpowiedz and wynik.intencja not in (Intencja.POZA_TEMATEM, Intencja.TERMINY):
            ui.button('Kopiuj', icon='content_copy', on_click=kopiuj).props(styl)
