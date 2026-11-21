"""Układ aplikacji (nagłówek, menu, routing) i uruchomienie okna."""

from nicegui import app, ui

from .strony import (strona_archiwum, strona_baza_wiedzy, strona_nowy_wniosek, strona_sprawa,
                     strona_ustawienia, strona_wnioski)

TYTUL = 'Asystent UDIP – UM Bydgoszcz'

MENU = [
    ('Wnioski', 'event_note', '/'),
    ('Nowy wniosek', 'note_add', '/nowy'),
    ('Archiwum', 'inventory_2', '/archiwum'),
    ('Baza wiedzy', 'menu_book', '/baza'),
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


def root() -> None:
    ui.add_css(CSS)
    ui.add_body_html(BLOKADA_UPUSZCZANIA)
    ui.query('body').classes('bg-grey-1')

    with ui.header().classes('items-center justify-between bg-primary q-px-md'):
        with ui.row().classes('items-center'):
            ui.icon('gavel', size='md')
            with ui.column().classes('gap-0'):
                ui.label('Asystent UDIP').classes('text-h6')
                ui.label('Urząd Miasta Bydgoszczy').classes('text-caption')
        with ui.row().classes('items-center gap-1 bg-green-8 rounded-borders q-px-sm q-py-xs'):
            ui.icon('lock')
            ui.label('Model lokalny · offline')

    with ui.left_drawer(value=True, bordered=True).props('width=230').classes('bg-white'):
        with ui.list().classes('w-full'):
            for nazwa, ikona, sciezka in MENU:
                with ui.item(on_click=lambda s=sciezka: ui.navigate.to(s)):
                    with ui.item_section().props('avatar'):
                        ui.icon(ikona, color='primary')
                    with ui.item_section():
                        ui.item_label(nazwa)

    with ui.column().classes('w-full q-pa-md'):
        ui.sub_pages({
            '/': strona_wnioski,
            '/nowy': strona_nowy_wniosek,
            '/sprawa/{id}': strona_sprawa,
            '/archiwum': strona_archiwum,
            '/baza': strona_baza_wiedzy,
            '/ustawienia': strona_ustawienia,
        })


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
