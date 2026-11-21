"""Ekran główny: kalendarz (lista) wniosków z terminami."""

from datetime import date

from nicegui import ui

from ... import rejestr
from ...rejestr import Wniosek
from ..komponenty import kafelek, naglowek_strony

KOLOR_STATUSU = {
    'brak': 'grey-6',
    'wydzialy': 'blue-7',
    'kwerenda': 'purple-6',
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
SLOT_STATUS = '''
<q-td :props="props" :class="props.row.klasa">
  <q-badge :color="props.row.kolor_statusu" :label="props.value" />
</q-td>
'''


def _data(d: date | None) -> str:
    return d.strftime('%d.%m.%Y') if d else '—'


def _wiersz(lp: int, w: Wniosek) -> dict:
    return {
        'id': w.id, 'lp': lp, 'nr': w.nr, 'temat': w.temat,
        'wplyw': _data(w.data_wplywu), 'termin': _data(w.termin), 'pozostalo': w.pozostalo,
        'status': w.status_opis, 'kolor_statusu': KOLOR_STATUSU[w.status],
        'kto': w.kto, 'odp': _data(w.data_odpowiedzi), 'klasa': KLASA_WIERSZA[w.pilnosc],
    }


def strona_wnioski() -> None:
    wnioski = rejestr.wszystkie()
    rok = date.today().year

    with ui.row().classes('w-full items-end justify-between'):
        naglowek_strony('Wnioski', 'Od najstarszych do najnowszych. Kliknij wiersz, żeby otworzyć sprawę.')
        with ui.row().classes('items-center'):
            widok = ui.toggle({'tabela': 'Tabela', 'miesiac': 'Miesiąc'}, value='tabela')
            ui.select([rok, rok - 1, rok - 2], value=rok, label='Rok').classes('w-28')
            ui.button('Nowy wniosek', icon='add', on_click=lambda: ui.navigate.to('/nowy'))

    pilnosci = [w.pilnosc for w in wnioski]
    with ui.row().classes('gap-4 my-2'):
        kafelek(pilnosci.count('po_terminie') + pilnosci.count('dzis'), 'termin dziś / po terminie', 'red-8')
        kafelek(pilnosci.count('jutro'), 'termin jutro', 'orange-8')
        kafelek(sum(w.status in ('wydzialy', 'przygotowana') for w in wnioski), 'w przygotowaniu', 'blue-8')
        kafelek(sum(w.status == 'kwerenda' for w in wnioski), 'kwerenda', 'purple-7')

    with ui.column().classes('w-full').bind_visibility_from(widok, 'value', value='tabela'):
        tabela = ui.table(columns=KOLUMNY, rows=[_wiersz(lp, w) for lp, w in enumerate(wnioski, start=1)],
                          row_key='id', pagination_controls=False) \
            .classes('w-full cursor-pointer').props('flat bordered')
        tabela.add_slot('body-cell', SLOT_KOMORKA)
        tabela.add_slot('body-cell-nr', SLOT_KOMORKA_POGRUBIONA)
        tabela.add_slot('body-cell-pozostalo', SLOT_KOMORKA_POGRUBIONA)
        tabela.add_slot('body-cell-status', SLOT_STATUS)
        tabela.on('rowClick', lambda e: ui.navigate.to(f'/sprawa/{e.args[1]["id"]}'))

        with ui.row().classes('gap-4 text-caption text-grey-8 items-center'):
            for klasa, opis in [('bg-red-2', 'po terminie'), ('bg-red-1', 'termin dziś'),
                                ('bg-orange-1', 'termin jutro'), ('bg-yellow-1', 'do 3 dni')]:
                with ui.row().classes('items-center gap-1'):
                    ui.element('div').classes(f'{klasa} w-4 h-4 rounded-borders border')
                    ui.label(opis)

    with ui.card().classes('w-full').props('flat bordered') \
            .bind_visibility_from(widok, 'value', value='miesiac'):
        ui.label('Widok miesiąca').classes('text-h6')
        ui.label('TODO: siatka miesiąca z wnioskami przypiętymi do dnia terminu.').classes('text-grey-7')
