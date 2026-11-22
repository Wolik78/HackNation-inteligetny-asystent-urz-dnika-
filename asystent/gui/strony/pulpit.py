"""Pulpit „Na dziś”: co pilne, na co czekamy od wydziałów, terminowość i liczba wniosków w miesiącach."""

from nicegui import ui

from ... import rejestr
from ...rejestr import Wniosek
from ...statystyki import policz
from ..komponenty import naglowek_strony, odmiana


def _kafelek(wartosc: str, opis: str, kolor: str, ikona: str) -> None:
    with ui.card().classes('col min-w-[10rem]').props('flat bordered'):
        with ui.row().classes('items-center gap-2 no-wrap'):
            ui.icon(ikona, color=kolor, size='sm')
            ui.label(opis).classes('text-caption text-grey-7')
        ui.label(wartosc).classes(f'text-h5 text-weight-medium text-{kolor}')


def _lista(tytul: str, wnioski: list[Wniosek], pusto: str, ikona: str) -> None:
    with ui.card().classes('col').props('flat bordered'):
        with ui.row().classes('items-center gap-2'):
            ui.icon(ikona, color='primary')
            ui.label(tytul).classes('text-subtitle1 text-weight-medium')
        if not wnioski:
            ui.label(pusto).classes('text-grey-7')
            return
        with ui.list().props('dense separator').classes('w-full'):
            for w in wnioski[:8]:
                with ui.item(on_click=lambda id=w.id: ui.navigate.to(f'/sprawa/{id}')).props('clickable'):
                    with ui.item_section():
                        ui.item_label(f'{w.nr} – {w.temat}').classes('ellipsis')
                        ui.item_label(f'termin {w.termin:%d.%m.%Y} ({w.pozostalo}) · {w.status_opis} · {w.kto}') \
                            .props('caption')
        if len(wnioski) > 8:
            ui.label(f'… i {odmiana(len(wnioski) - 8, "kolejny", "kolejne", "kolejnych")}').classes('text-caption')


def strona_pulpit() -> None:
    naglowek_strony('Na dziś', 'Co wymaga uwagi teraz i jak idzie obsługa wniosków.')
    s = policz(rejestr.wszystkie())

    with ui.row().classes('w-full gap-3'):
        _kafelek(str(s.w_toku), 'w toku', 'primary', 'pending_actions')
        _kafelek(str(len(s.na_dzis) + len(s.na_jutro)), 'termin dziś lub jutro', 'orange-9', 'today')
        _kafelek(str(len(s.po_terminie)), 'po terminie', 'negative' if s.po_terminie else 'grey-7', 'warning')
        _kafelek(str(len(s.czekamy_na_wydzialy)), 'czekamy na wydziały', 'blue-8', 'forward_to_inbox')
        _kafelek(f'{s.w_terminie_procent}%' if s.w_terminie_procent is not None else '—',
                 'odpowiedzi w terminie', 'positive', 'verified')
        _kafelek(f'{s.sredni_czas_dni:.1f} dni'.replace('.', ',') if s.sredni_czas_dni is not None else '—',
                 'średni czas odpowiedzi', 'teal', 'timer')

    with ui.row().classes('w-full gap-3 items-stretch'):
        _lista('Pilne: po terminie, dziś i jutro', s.po_terminie + s.na_dzis + s.na_jutro,
               'Nic pilnego – wszystkie terminy są dalej niż jutro.', 'priority_high')
        _lista('Czekamy na odpowiedzi wydziałów', s.czekamy_na_wydzialy,
               'Żadna sprawa nie czeka na wydziały.', 'forward_to_inbox')

    with ui.row().classes('w-full gap-3 items-stretch'):
        with ui.card().classes('col-8').props('flat bordered'):
            ui.label('Wpływ wniosków – ostatnie 12 miesięcy').classes('text-subtitle1 text-weight-medium')
            ui.echart({
                'grid': {'left': 30, 'right': 10, 'top': 20, 'bottom': 30},
                'tooltip': {'trigger': 'axis'},
                'xAxis': {'type': 'category', 'data': [m for m, _ in s.miesiecznie]},
                'yAxis': {'type': 'value', 'minInterval': 1},
                'series': [{'type': 'bar', 'data': [n for _, n in s.miesiecznie], 'name': 'wnioski',
                            'itemStyle': {'color': '#1F4E79'}}],
            }).classes('w-full h-56')
        with ui.card().classes('col').props('flat bordered'):
            ui.label('Rodzaje spraw').classes('text-subtitle1 text-weight-medium')
            for nazwa, liczba in s.wg_rodzaju:
                with ui.row().classes('w-full justify-between no-wrap'):
                    ui.label(nazwa).classes('text-body2')
                    ui.label(str(liczba)).classes('text-weight-medium')
            ui.label(f'Kwerendy w toku: {s.kwerendy} · wysłane odpowiedzi: {s.wyslane}') \
                .classes('text-caption text-grey-7 q-mt-sm')
