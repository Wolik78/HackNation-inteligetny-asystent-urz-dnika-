"""Ekran główny: kalendarz wniosków – lista od najstarszych i widok miesiąca, z terminami i statusami."""

import calendar
from datetime import date, timedelta

from nicegui import run, ui

from ... import rejestr
from ...eksport_rejestru import do_excela, do_kalendarza
from ...konfiguracja import KATALOG_DANYCH
from ...rejestr import Wniosek
from ...terminy import NAZWY_DNI_KROTKIE, NAZWY_MIESIECY, jest_dniem_wolnym, powod_wolnego
from ..komponenty import naglowek_strony, odmiana, zapisz_jako

KOLOR_STATUSU = {
    'brak': 'grey-6',
    'wydzialy': 'blue-7',
    'przygotowana': 'orange-8',
    'wyslana': 'green-7',
}

KLASA_WIERSZA = {
    'po_terminie': 'bg-red-2',
    'dzis': 'bg-red-1',
    'jutro': 'bg-orange-1',
    'blisko': 'bg-yellow-1',
    'wyslano': 'text-grey-6',
    'ok': '',
}

KLASA_ZNACZNIKA = {  # znaczniki wniosków w widoku miesiąca
    'po_terminie': 'bg-red-6 text-white',
    'dzis': 'bg-red-4 text-white',
    'jutro': 'bg-orange-5 text-white',
    'blisko': 'bg-yellow-6 text-grey-10',
    'ok': 'bg-blue-1 text-blue-10',
    'wyslano': 'bg-green-1 text-green-9',
}

FILTRY = {
    'wszystkie': ('Wszystkie', lambda w: True),
    'pilne': ('Pilne', lambda w: w.pilnosc in ('po_terminie', 'dzis', 'jutro', 'blisko')),
    'w_toku': ('W toku', lambda w: w.status != 'wyslana'),
    'kwerendy': ('Kwerendy', lambda w: w.kwerenda and w.status != 'wyslana'),
    'wyslane': ('Wysłane', lambda w: w.status == 'wyslana'),
}

KOLUMNY = [
    {'name': 'lp', 'label': 'Lp.', 'field': 'lp', 'align': 'left'},
    {'name': 'nr', 'label': 'Nr wniosku', 'field': 'nr', 'align': 'left'},
    {'name': 'temat', 'label': 'Temat (skrót)', 'field': 'temat', 'align': 'left'},
    {'name': 'wplyw', 'label': 'Data wpływu', 'field': 'wplyw', 'align': 'left'},
    {'name': 'termin', 'label': 'Termin', 'field': 'termin', 'align': 'left'},
    {'name': 'pozostalo', 'label': 'Pozostało', 'field': 'pozostalo', 'align': 'left'},
    {'name': 'status', 'label': 'Status', 'field': 'status', 'align': 'left'},
    {'name': 'kto', 'label': 'Inicjały', 'field': 'kto', 'align': 'left'},
    {'name': 'odp', 'label': 'Data odpowiedzi', 'field': 'odp', 'align': 'left'},
]

# Kolor wiersza nakładamy na każdą komórkę (Quasar nie ma klasy dla całego wiersza),
# dzięki temu zostaje wbudowane zdarzenie rowClick.
SLOT_KOMORKA = '<q-td :props="props" :class="props.row.klasa">{{ props.value }}</q-td>'
SLOT_KOMORKA_POGRUBIONA = \
    '<q-td :props="props" :class="props.row.klasa" class="text-weight-medium">{{ props.value }}</q-td>'
SLOT_TEMAT = '''
<q-td :props="props" :class="props.row.klasa" style="white-space: normal; min-width: 220px">
  <div>{{ props.value }}</div>
  <div class="text-caption text-grey-7">{{ props.row.wnioskodawca }}</div>
</q-td>
'''
SLOT_TERMIN = '''
<q-td :props="props" :class="props.row.klasa">
  {{ props.value }}
  <q-icon v-if="props.row.uwaga" name="info_outline" size="xs" class="q-ml-xs text-grey-7">
    <q-tooltip>{{ props.row.uwaga }}</q-tooltip>
  </q-icon>
  <q-badge v-if="props.row.kwerenda" color="purple-1" text-color="purple-9" class="q-ml-xs"
           :label="'kwerenda +' + props.row.dni_kwerendy + ' dni'" />
</q-td>
'''
SLOT_STATUS = '''
<q-td :props="props" :class="props.row.klasa">
  <q-badge :color="props.row.kolor_statusu" :label="props.value" />
</q-td>
'''


def _data(d: date | None) -> str:
    return d.strftime('%d.%m.%Y') if d else '—'


def _wiersz(lp: int, w: Wniosek) -> dict:
    return {
        'id': w.id, 'lp': lp, 'nr': w.nr, 'temat': w.temat, 'wnioskodawca': w.wnioskodawca,
        'wplyw': _data(w.data_wplywu), 'termin': _data(w.termin), 'pozostalo': w.pozostalo,
        'uwaga': w.uwaga_o_terminie, 'kwerenda': w.kwerenda, 'dni_kwerendy': w.dni_kwerendy,
        'status': w.status_opis, 'kolor_statusu': KOLOR_STATUSU[w.status],
        'kto': w.kto, 'odp': _data(w.data_odpowiedzi), 'klasa': KLASA_WIERSZA[w.pilnosc],
    }


def _kafelek(liczba: int, opis: str, kolor: str, na_klik) -> None:
    with ui.card().classes('w-52 cursor-pointer').props('flat bordered').on('click', na_klik) \
            .tooltip('Kliknij, żeby pokazać te wnioski'):
        ui.label(str(liczba)).classes(f'text-h4 text-weight-medium text-{kolor}')
        ui.label(opis).classes('text-grey-7')


def strona_wnioski() -> None:
    stan = {'rok': date.today().year, 'filtr': 'wszystkie', 'szukaj': '', 'kto': None,
            'miesiac': date.today().replace(day=1)}

    def wnioski_roku() -> list[Wniosek]:
        return rejestr.wszystkie(stan['rok'])

    def pasuje(w: Wniosek) -> bool:
        fraza = (stan['szukaj'] or '').strip().lower()
        if fraza and fraza not in f'{w.nr} {w.temat} {w.wnioskodawca}'.lower():
            return False
        if stan['kto'] and w.kto != stan['kto']:
            return False
        return FILTRY[stan['filtr']][1](w)

    def ustaw_filtr(filtr: str) -> None:
        stan['filtr'] = filtr
        przelacznik_filtrow.set_value(filtr)

    def odswiez() -> None:
        kafelki.refresh()
        lista.refresh()
        kalendarz.refresh()
        przelacznik_filtrow.set_options(
            {k: f'{nazwa} {sum(1 for w in wnioski_roku() if f(w))}' for k, (nazwa, f) in FILTRY.items()},
            value=stan['filtr'])

    # --- nagłówek ---
    with ui.row().classes('w-full items-end justify-between'):
        naglowek_strony('Wnioski', 'Od najstarszych do najnowszych. Kliknij wiersz, żeby otworzyć sprawę.')
        with ui.row().classes('items-center'):
            widok = ui.toggle({'tabela': 'Tabela', 'miesiac': 'Miesiąc'}, value='tabela')
            ui.select(rejestr.lata(), value=stan['rok'], label='Rok',
                      on_change=lambda e: (stan.update(rok=e.value), odswiez())).classes('w-28')
            with ui.button(icon='file_download').props('flat round').tooltip('Eksport rejestru'):
                with ui.menu():
                    ui.menu_item('Rejestr do Excela (.xlsx)', on_click=lambda: eksportuj('xlsx'))
                    ui.menu_item('Terminy do kalendarza Outlook (.ics)', on_click=lambda: eksportuj('ics'))
            ui.button('Nowy wniosek', icon='add', on_click=lambda: ui.navigate.to('/nowy'))

    async def eksportuj(format: str) -> None:
        wnioski = wnioski_roku()
        katalog = KATALOG_DANYCH / 'eksport'
        if format == 'xlsx':
            plik = await run.io_bound(do_excela, wnioski, katalog / f'rejestr_wnioskow_{stan["rok"]}.xlsx')
            await zapisz_jako(plik, 'Skoroszyt Excel')
        else:
            plik = await run.io_bound(do_kalendarza, wnioski, katalog / f'terminy_wnioskow_{stan["rok"]}.ics')
            await zapisz_jako(plik, 'Kalendarz iCalendar')
            ui.notify('Otwórz plik .ics w Outlooku – terminy spraw w toku pojawią się z przypomnieniem '
                      'dzień wcześniej.', type='info')

    # --- kafelki ---
    @ui.refreshable
    def kafelki() -> None:
        wnioski = wnioski_roku()
        pilnosci = [w.pilnosc for w in wnioski]
        with ui.row().classes('gap-4 my-2'):
            _kafelek(pilnosci.count('po_terminie') + pilnosci.count('dzis'), 'termin dziś / po terminie', 'red-8',
                     lambda: ustaw_filtr('pilne'))
            _kafelek(pilnosci.count('jutro'), 'termin w najbliższy dzień roboczy', 'orange-8',
                     lambda: ustaw_filtr('pilne'))
            _kafelek(sum(w.status in ('wydzialy', 'przygotowana') for w in wnioski), 'w przygotowaniu', 'blue-8',
                     lambda: ustaw_filtr('w_toku'))
            _kafelek(sum(w.kwerenda and w.status != 'wyslana' for w in wnioski), 'kwerendy', 'purple-7',
                     lambda: ustaw_filtr('kwerendy'))

    kafelki()

    # --- filtry ---
    with ui.row().classes('w-full items-center gap-3'):
        przelacznik_filtrow = ui.toggle({k: nazwa for k, (nazwa, _) in FILTRY.items()}, value='wszystkie',
                                        on_change=lambda e: (stan.update(filtr=e.value), lista.refresh(),
                                                             kalendarz.refresh())).props('no-caps')
        ui.input(placeholder='Szukaj: numer, temat, wnioskodawca',
                 on_change=lambda e: (stan.update(szukaj=e.value), lista.refresh(), kalendarz.refresh())) \
            .props('dense outlined clearable').classes('w-80')
        prowadzacy = sorted({w.kto for w in rejestr.wszystkie() if w.kto})
        ui.select({None: 'Wszyscy prowadzący', **{k: k for k in prowadzacy}}, value=None, label='Prowadzi',
                  on_change=lambda e: (stan.update(kto=e.value), lista.refresh(), kalendarz.refresh())) \
            .props('dense outlined').classes('w-48')

    # --- tabela ---
    with ui.column().classes('w-full').bind_visibility_from(widok, 'value', value='tabela'):
        @ui.refreshable
        def lista() -> None:
            wiersze = [_wiersz(lp, w) for lp, w in enumerate(wnioski_roku(), start=1) if pasuje(w)]
            if not wiersze:
                with ui.card().classes('w-full items-center q-pa-lg').props('flat bordered'):
                    ui.icon('search_off', size='lg', color='grey-6')
                    ui.label('Brak wniosków spełniających kryteria.').classes('text-grey-7')
                return
            tabela = ui.table(columns=KOLUMNY, rows=wiersze, row_key='id', pagination_controls=False) \
                .classes('w-full cursor-pointer').props('flat bordered')
            tabela.add_slot('body-cell', SLOT_KOMORKA)
            tabela.add_slot('body-cell-nr', SLOT_KOMORKA_POGRUBIONA)
            tabela.add_slot('body-cell-pozostalo', SLOT_KOMORKA_POGRUBIONA)
            tabela.add_slot('body-cell-temat', SLOT_TEMAT)
            tabela.add_slot('body-cell-termin', SLOT_TERMIN)
            tabela.add_slot('body-cell-status', SLOT_STATUS)
            tabela.on('rowClick', lambda e: ui.navigate.to(f'/sprawa/{e.args[1]["id"]}'))

        lista()
        _legenda()

    # --- widok miesiąca ---
    with ui.column().classes('w-full').bind_visibility_from(widok, 'value', value='miesiac'):
        @ui.refreshable
        def kalendarz() -> None:
            _siatka_miesiaca(stan, [w for w in rejestr.wszystkie() if pasuje(w)], kalendarz.refresh)

        kalendarz()

    odswiez()


def _legenda() -> None:
    with ui.row().classes('gap-4 text-caption text-grey-8 items-center'):
        for klasa, opis in [('bg-red-2', 'po terminie'), ('bg-red-1', 'termin dziś'),
                            ('bg-orange-1', 'najbliższy dzień roboczy'), ('bg-yellow-1', 'do 3 dni roboczych')]:
            with ui.row().classes('items-center gap-1'):
                ui.element('div').classes(f'{klasa} w-4 h-4 rounded-borders border')
                ui.label(opis)
        with ui.row().classes('items-center gap-1'):
            ui.icon('info_outline', size='xs')
            ui.label('termin przesunięty z weekendu lub święta (art. 57 § 4 KPA)')


def _siatka_miesiaca(stan: dict, wnioski: list[Wniosek], odswiez) -> None:
    """Miesiąc w siatce pon–niedz; wniosek widnieje w dniu swojego terminu."""
    pierwszy: date = stan['miesiac']
    dzis = date.today()

    def zmien_miesiac(przesuniecie: int) -> None:
        indeks = pierwszy.month - 1 + przesuniecie
        stan['miesiac'] = date(pierwszy.year + indeks // 12, indeks % 12 + 1, 1)
        odswiez()

    def pokaz_dzisiaj() -> None:
        stan['miesiac'] = dzis.replace(day=1)
        odswiez()

    ostatni = pierwszy.replace(day=calendar.monthrange(pierwszy.year, pierwszy.month)[1])
    poczatek = pierwszy - timedelta(days=pierwszy.weekday())
    koniec = ostatni + timedelta(days=6 - ostatni.weekday())
    w_dniu: dict[date, list[Wniosek]] = {}
    for w in wnioski:
        if poczatek <= w.termin <= koniec:
            w_dniu.setdefault(w.termin, []).append(w)

    w_miesiacu = sum(len(v) for d, v in w_dniu.items() if d.month == pierwszy.month)
    with ui.row().classes('w-full items-center justify-between'):
        with ui.row().classes('items-center'):
            ui.button(icon='chevron_left', on_click=lambda: zmien_miesiac(-1)).props('flat round')
            ui.label(f'{NAZWY_MIESIECY[pierwszy.month - 1].capitalize()} {pierwszy.year}') \
                .classes('text-h6 text-weight-medium w-48 text-center')
            ui.button(icon='chevron_right', on_click=lambda: zmien_miesiac(1)).props('flat round')
            ui.button('Dziś', on_click=pokaz_dzisiaj).props('flat dense no-caps')
        ui.label(f'Terminy w tym miesiącu: {odmiana(w_miesiacu, "wniosek", "wnioski", "wniosków")}') \
            .classes('text-grey-7')

    with ui.element('div').classes('w-full').style(
            'display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 4px'):
        for nazwa in NAZWY_DNI_KROTKIE:
            ui.label(nazwa).classes('text-caption text-grey-7 text-center')
        dzien = poczatek
        while dzien <= koniec:
            inny_miesiac = dzien.month != pierwszy.month
            wolny = jest_dniem_wolnym(dzien)
            klasy = 'rounded-borders q-pa-xs column gap-1 ' + ('bg-grey-2' if wolny else 'bg-white')
            styl = 'min-height: 92px; border: 1px solid #e0e0e0;' + (' opacity: .45;' if inny_miesiac else '')
            if dzien == dzis:
                styl += ' border: 2px solid var(--q-primary);'
            with ui.element('div').classes(klasy).style(styl):
                with ui.row().classes('items-center justify-between no-wrap w-full'):
                    ui.label(str(dzien.day)).classes('text-caption text-weight-medium' +
                                                     (' text-primary' if dzien == dzis else ''))
                    if wolny and dzien.weekday() < 5:
                        ui.icon('celebration', size='xs', color='grey-6').tooltip(powod_wolnego(dzien))
                for w in w_dniu.get(dzien, []):
                    ui.label(w.nr).classes(f'text-caption rounded-borders q-px-xs cursor-pointer ellipsis '
                                           f'{KLASA_ZNACZNIKA[w.pilnosc]}') \
                        .tooltip(f'{w.temat} · {w.status_opis}') \
                        .on('click', lambda _, id=w.id: ui.navigate.to(f'/sprawa/{id}'))
            dzien += timedelta(days=1)
