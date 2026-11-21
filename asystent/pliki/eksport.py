"""Zapis projektu odpowiedzi do pliku Word (.docx) lub tekstowego (.txt)."""

from pathlib import Path

FORMATY = {
    'docx': 'Dokument Word (*.docx)',
    'txt': 'Plik tekstowy (*.txt)',
}


def nazwa_pliku_odpowiedzi(nr_sprawy: str, format: str) -> str:
    bezpieczny_nr = ''.join(z if z.isalnum() or z in '.-' else '_' for z in nr_sprawy)
    return f'Odpowiedz_{bezpieczny_nr}.{format}'


def eksportuj(tekst: str, sciezka: Path) -> Path:
    """Zapisuje tekst w formacie wynikającym z rozszerzenia ścieżki."""
    sciezka = Path(sciezka)
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    if sciezka.suffix.lower() == '.docx':
        _do_docx(tekst, sciezka)
    elif sciezka.suffix.lower() == '.txt':
        sciezka.write_text(tekst, encoding='utf-8', newline='\r\n')  # \r\n – poprawnie w Notatniku
    else:
        raise ValueError(f'Nieobsługiwany format eksportu: {sciezka.suffix}')
    return sciezka


def _do_docx(tekst: str, sciezka: Path) -> None:
    import docx
    from docx.shared import Pt

    dokument = docx.Document()
    styl = dokument.styles['Normal']
    styl.font.name = 'Arial'
    styl.font.size = Pt(11)
    styl.paragraph_format.space_after = Pt(0)

    # Każda linia to osobny akapit (pusta linia = pusty akapit), więc pismo wygląda jak w edytorze.
    for linia in tekst.replace('\r\n', '\n').split('\n'):
        dokument.add_paragraph(linia)
    dokument.save(str(sciezka))
