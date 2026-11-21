"""Baza wiedzy: ustawy, zarządzenia i archiwalne odpowiedzi, z których korzysta asystent."""

from nicegui import background_tasks, run, ui

from ...ai import BladAI
from ...pliki import KATEGORIE_BAZY_WIEDZY, Kategoria, ZapisanyPlik
from ...uslugi import archiwum, magazyn
from ..komponenty import WgranePliki, karta_pliku, naglowek_strony, odmiana, strefa_wgrywania, zapisz_wgrane

MAKS_NA_LISCIE = 100


async def _zaindeksuj_archiwum() -> None:
    try:
        await archiwum.zaindeksuj()
    except BladAI:
        pass  # LM Studio wyłączone – wektory policzą się przy pierwszym wyszukiwaniu (a do tego czasu – po słowach)


def strona_baza_wiedzy() -> None:
    naglowek_strony('Baza wiedzy', 'Dokumenty, na podstawie których asystent szuka podobnych spraw '
                                   'i przygotowuje odpowiedzi.')

    async def wgraj(pliki: WgranePliki) -> None:
        kat = Kategoria(kategoria.value)
        if await zapisz_wgrane(pliki, lambda n, d: magazyn.zapisz(d, n, kat)):
            lista.refresh()
            if kat == Kategoria.ARCHIWUM:  # wektory nowych odpowiedzi liczą się w tle – wyszukiwanie będzie od razu
                background_tasks.create(_zaindeksuj_archiwum(), name='indeks archiwum')

    async def usun(plik: ZapisanyPlik) -> None:
        await run.io_bound(magazyn.usun, plik)
        lista.refresh()

    with ui.row().classes('w-full gap-6 items-start no-wrap'):
        with ui.card().classes('w-[26rem] shrink-0').props('flat bordered'):
            ui.label('Dodaj dokumenty').classes('text-subtitle1 text-weight-medium')
            kategoria = ui.select({k.value: k.etykieta for k in KATEGORIE_BAZY_WIEDZY},
                                  value=Kategoria.USTAWA.value, label='Rodzaj dokumentów').classes('w-full')
            strefa_wgrywania(wgraj, tytul='Przeciągnij tutaj dokumenty', wiele=True)
            ui.label('Możesz upuścić wiele plików naraz, np. całe archiwum odpowiedzi z danego roku. '
                     'Powtórnie wgrane pliki są wykrywane i pomijane.').classes('text-caption text-grey-7')

        with ui.column().classes('col'):
            with ui.row().classes('w-full items-center'):
                filtr = ui.toggle({'wszystkie': 'Wszystkie', **{k.value: k.etykieta for k in KATEGORIE_BAZY_WIEDZY}},
                                  value='wszystkie', on_change=lambda: lista.refresh())
                szukaj = ui.input(placeholder='Filtruj po nazwie pliku', on_change=lambda: lista.refresh()) \
                    .props('dense outlined clearable').classes('w-64')

            @ui.refreshable
            def lista() -> None:
                kategorie = KATEGORIE_BAZY_WIEDZY if filtr.value == 'wszystkie' else (Kategoria(filtr.value),)
                pliki = [p for k in kategorie for p in magazyn.lista(k)]
                fraza = (szukaj.value or '').lower()
                if fraza:
                    pliki = [p for p in pliki if fraza in p.nazwa_oryginalna.lower()]
                pliki.sort(key=lambda p: p.dodano, reverse=True)

                if not pliki:
                    with ui.column().classes('w-full items-center q-pa-xl text-grey-7'):
                        ui.icon('library_books', size='xl')
                        ui.label('Brak dokumentów. Dodaj ustawy, zarządzenia albo archiwalne odpowiedzi.')
                    return
                ui.label(odmiana(len(pliki), 'dokument', 'dokumenty', 'dokumentów')).classes('text-grey-7')
                for plik in pliki[:MAKS_NA_LISCIE]:
                    karta_pliku(plik, on_usun=usun)
                if len(pliki) > MAKS_NA_LISCIE:
                    ui.label(f'Pokazano {MAKS_NA_LISCIE} najnowszych – zawęź listę filtrem.') \
                        .classes('text-caption text-grey-7')

            lista()
