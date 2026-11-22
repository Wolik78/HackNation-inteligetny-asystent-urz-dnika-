"""Układ aplikacji (nagłówek, menu, routing) i uruchomienie okna."""

from collections.abc import Callable

from nicegui import app, ui

from ..uslugi import bielik
from .czat import panel_czatu
from .kontekst import biezacy
from .strony import (strona_anonimizacja, strona_archiwum, strona_baza_wiedzy, strona_dziennik_ai,
                     strona_nowy_wniosek, strona_pulpit, strona_sprawa, strona_ustawienia, strona_wnioski)

TYTUL = 'Cyfrowy Ratusz – UM Bydgoszcz'

MENU = [
    ('Wnioski', 'event_note', '/'),
    ('Na dziś', 'dashboard', '/pulpit'),
    ('Nowy wniosek', 'note_add', '/nowy'),
    ('Archiwum', 'inventory_2', '/archiwum'),
    ('Anonimizacja pliku', 'visibility_off', '/anonimizacja'),
    ('Baza wiedzy', 'menu_book', '/baza'),
    ('Dziennik AI', 'fact_check', '/dziennik'),
    ('Ustawienia', 'settings', '/ustawienia'),
]

CSS = '''
.strefa-wgrywania { width: 100%; max-height: none; border: 2px dashed #9ca3af; border-radius: 12px; }
.strefa-wgrywania:hover { border-color: var(--q-primary); }
.strefa-wgrywania .q-uploader__list { display: none; }
'''

# Upuszczenie pliku poza polem wgrywania otworzyłoby go w oknie zamiast aplikacji – blokujemy to.
BLOKADA_UPUSZCZANIA = '''
<script>
window.addEventListener('dragover', (e) => {
  e.preventDefault();
  if (!e.target.closest('.q-uploader')) e.dataTransfer.dropEffect = 'none';
});
window.addEventListener('drop', (e) => e.preventDefault());
</script>
'''


def wskaznik_modelu() -> None:
    """Etykieta w nagłówku pokazująca na żywo, czy lokalny Bielik jest dostępny."""
    with ui.row().classes('items-center gap-1 rounded-borders q-px-sm q-py-xs bg-grey-7') as etykieta:
        ikona = ui.icon('hourglass_empty')
        tekst = ui.label('Sprawdzam Bielika…')
        podpowiedz = ui.tooltip('')

    async def sprawdz() -> None:
        status = await bielik.status()
        etykieta.classes(replace='items-center gap-1 rounded-borders q-px-sm q-py-xs '
                                 + ('bg-green-8' if status.dostepny else 'bg-red-8'))
        ikona.name = 'lock' if status.dostepny else 'cloud_off'
        tekst.set_text('Bielik lokalnie · offline' if status.dostepny else 'Bielik niedostępny')
        podpowiedz.set_text(status.komunikat)

    ui.timer(15, sprawdz)
    ui.timer(0.1, sprawdz, once=True)


def root() -> None:
    ui.add_css(CSS)
    ui.add_body_html(BLOKADA_UPUSZCZANIA)
    ui.query('body').classes('bg-grey-1')

    with ui.header().classes('items-center justify-between bg-primary q-px-md'):
        with ui.row().classes('items-center'):
            ui.icon('gavel', size='md')
            with ui.column().classes('gap-0'):
                ui.label('Cyfrowy Ratusz').classes('text-h6')
                ui.label('Urząd Miasta Bydgoszczy').classes('text-caption')
        with ui.row().classes('items-center gap-3'):
            ui.button('Urzęduś', icon='smart_toy', on_click=lambda: panel_urzedusia.toggle()) \
                .props('unelevated no-caps color=white text-color=primary').tooltip('Asystent AI')
            wskaznik_modelu()

    with ui.left_drawer(value=True, bordered=True).props('width=230').classes('bg-white'):
        with ui.list().classes('w-full'):
            for nazwa, ikona, sciezka in MENU:
                with ui.item(on_click=lambda s=sciezka: ui.navigate.to(s)):
                    with ui.item_section().props('avatar'):
                        ui.icon(ikona, color='primary')
                    with ui.item_section():
                        ui.item_label(nazwa)

    with ui.right_drawer(value=False, bordered=True).props('width=440').classes('bg-white') as panel_urzedusia:
        with ui.column().classes('w-full h-full no-wrap gap-2'):
            panel_czatu(zamknij=panel_urzedusia.hide)

    with ui.column().classes('w-full q-pa-md'):
        ui.sub_pages({
            '/': _bez_sprawy(strona_wnioski),
            '/pulpit': _bez_sprawy(strona_pulpit),
            '/nowy': _bez_sprawy(strona_nowy_wniosek),
            '/sprawa/{id}': strona_sprawa,  # sama ustawia kontekst sprawy dla Urzędusia
            '/archiwum': _bez_sprawy(strona_archiwum),
            '/anonimizacja': _bez_sprawy(strona_anonimizacja),
            '/baza': _bez_sprawy(strona_baza_wiedzy),
            '/dziennik': _bez_sprawy(strona_dziennik_ai),
            '/ustawienia': _bez_sprawy(strona_ustawienia),
        })


def _bez_sprawy(strona: Callable[[], None]) -> Callable[[], None]:
    """Ekran bez otwartej sprawy – Urzęduś przestaje na niej pracować."""
    def opakowana() -> None:
        biezacy().zamknij_sprawe()
        strona()
    return opakowana


def uruchom(*, tryb_web: bool = False) -> None:
    """Startuje aplikację: domyślnie w oknie desktopowym, z tryb_web=True w przeglądarce."""
    app.colors(primary='#1f4e79')
    ui.run(
        root,
        title=TYTUL,
        language='pl',
        native=not tryb_web,
        window_size=None if tryb_web else (1400, 900),
        host='127.0.0.1',  # tylko lokalnie – nie wystawiamy aplikacji w sieci
        port=8080 if tryb_web else None,
        show=False,
        reload=False,
    )
