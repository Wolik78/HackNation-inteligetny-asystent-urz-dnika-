"""Wspólne fikstury: generują przykładowe dokumenty w locie, bez prawdziwych danych osobowych."""

import io
import os
import tempfile
from pathlib import Path

# Testy nigdy nie piszą do prawdziwego folderu danych – ustawiamy go, zanim cokolwiek zaimportuje `asystent`.
os.environ['UDIP_KATALOG_DANYCH'] = tempfile.mkdtemp(prefix='udip_testy_')

import docx
import pytest
from fpdf import FPDF

CZCIONKA_TTF = Path(r'C:\Windows\Fonts\arial.ttf')
TEKST_PL = 'Wniosek o udostępnienie informacji publicznej – zażółć gęślą jaźń'

# Fikcyjne dokumenty z repozytorium (opis: dane_testowe/README.md)
DANE_TESTOWE = Path(__file__).resolve().parents[1] / 'dane_testowe'
WNIOSEK_TESTOWY = DANE_TESTOWE / 'wnioski' / 'wniosek_wydatki_na_promocje.pdf'
ARCHIWUM_TESTOWE = DANE_TESTOWE / 'archiwum'
WNIOSEK_Z_DANYMI = DANE_TESTOWE / 'anonimizacja' / 'wniosek_z_danymi_osobowymi.pdf'
WNIOSEK_Z_DANYMI_SKAN = DANE_TESTOWE / 'anonimizacja' / 'wniosek_z_danymi_osobowymi_skan.pdf'


def zrob_pdf(tekst: str | None = TEKST_PL, strony: int = 1) -> bytes:
    """PDF z tekstem (z polskimi znakami, jeśli dostępna jest czcionka TTF) albo pusty (jak skan)."""
    pdf = FPDF()
    if tekst and CZCIONKA_TTF.exists():
        pdf.add_font('Arial', fname=str(CZCIONKA_TTF))
        pdf.set_font('Arial', size=12)
    else:
        pdf.set_font('Helvetica', size=12)
        tekst = tekst and tekst.encode('ascii', 'ignore').decode()
    for _ in range(strony):
        pdf.add_page()
        if tekst:
            pdf.multi_cell(0, 10, tekst)
    return bytes(pdf.output())


def zrob_docx(akapity: list[str], tabela: list[list[str]] | None = None) -> bytes:
    dokument = docx.Document()
    for akapit in akapity:
        dokument.add_paragraph(akapit)
    if tabela:
        t = dokument.add_table(rows=len(tabela), cols=len(tabela[0]))
        for i, wiersz in enumerate(tabela):
            for j, wartosc in enumerate(wiersz):
                t.cell(i, j).text = wartosc
    bufor = io.BytesIO()
    dokument.save(bufor)
    return bufor.getvalue()


@pytest.fixture
def ma_polska_czcionke() -> bool:
    return CZCIONKA_TTF.exists()
