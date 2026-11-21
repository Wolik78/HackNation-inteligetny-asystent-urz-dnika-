"""Kontekst okna: która sprawa jest teraz otwarta – żeby Urzęduś pracował na jej dokumentach.

Każde okno (klient NiceGUI) ma własny kontekst, więc kilka okien nie miesza sobie spraw.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from nicegui import ui

from ..rejestr import Wniosek

log = logging.getLogger(__name__)


@dataclass
class KontekstOkna:
    wniosek: Wniosek | None = None
    stan_sprawy: dict | None = None  # stan widoku sprawy: projekt, wykryte i ukryte dane osobowe…
    _odswiez_sprawe: list[Callable[[], None]] = field(default_factory=list)
    _po_zmianie: list[Callable[[], None]] = field(default_factory=list)

    def otworz_sprawe(self, wniosek: Wniosek, stan: dict, odswiezacze: list[Callable[[], None]]) -> None:
        self.wniosek, self.stan_sprawy, self._odswiez_sprawe = wniosek, stan, list(odswiezacze)
        self._powiadom()

    def zamknij_sprawe(self) -> None:
        if self.wniosek is None:
            return
        self.wniosek, self.stan_sprawy, self._odswiez_sprawe = None, None, []
        self._powiadom()

    def po_zmianie_sprawy(self, funkcja: Callable[[], None]) -> None:
        self._po_zmianie.append(funkcja)

    def odswiez_widok_sprawy(self) -> None:
        """Po zastosowaniu zmian z czatu – odświeża kroki sprawy, które od nich zależą."""
        for funkcja in self._odswiez_sprawe:
            try:
                funkcja()
            except Exception:  # widok mógł zostać już zamknięty
                log.debug('Nie udało się odświeżyć widoku sprawy', exc_info=True)

    def _powiadom(self) -> None:
        for funkcja in self._po_zmianie:
            funkcja()


_konteksty: dict[str, KontekstOkna] = {}


def biezacy() -> KontekstOkna:
    klient = ui.context.client
    if klient.id not in _konteksty:
        _konteksty[klient.id] = KontekstOkna()
        klient.on_delete(lambda: _konteksty.pop(klient.id, None))
    return _konteksty[klient.id]
