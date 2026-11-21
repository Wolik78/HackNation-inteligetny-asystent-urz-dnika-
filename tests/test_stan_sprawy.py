from asystent import stan_sprawy
from asystent.ai import Zadanie
from asystent.kontrola import sprawdz_pismo

PROJEKT = 'Szanowny Panie Janie Testowy, wydano 1 240 000 zł oraz 999 000 zł. Z poważaniem'


def _stan(**zmiany) -> dict:
    stan = {
        'projekt': PROJEKT,
        'ukryte': {'Janie Testowy'},
        'wykryte': {'Janie Testowy': 'Dane osobowe (Bielik)'},
        'kontrola': sprawdz_pismo(PROJEKT, [('odpowiedz.docx', 'Wydano 1 240 000 zł.')]),
        'kontrola_tekst': PROJEKT,
        'kompletnosc': [Zadanie('ile wydano', True, 'wydano 1 240 000 zł'), Zadanie('kopie umów', False)],
        'szablon': 'nie zapisujemy', 'generowanie': True,
    }
    stan.update(zmiany)
    return stan


def test_zapis_i_odczyt(tmp_path):
    stan = _stan()
    stan_sprawy.zapisz(tmp_path / 'UDIP.11.2026', stan)
    wczytany = stan_sprawy.wczytaj(tmp_path / 'UDIP.11.2026')

    assert wczytany['projekt'] == PROJEKT
    assert wczytany['ukryte'] == {'Janie Testowy'}
    assert wczytany['wykryte'] == stan['wykryte']
    assert wczytany['kontrola'] == stan['kontrola']          # dataclassy po odtworzeniu są równe
    assert [p.fragment for p in wczytany['kontrola'].bledy] == ['999 000']
    assert wczytany['kompletnosc'] == stan['kompletnosc']
    assert 'zapisano' in wczytany
    assert 'szablon' not in wczytany and 'generowanie' not in wczytany


def test_brak_zapisu(tmp_path):
    assert stan_sprawy.wczytaj(tmp_path) == {}


def test_przerwana_ocena_kompletnosci_nie_jest_zapisywana(tmp_path):
    stan_sprawy.zapisz(tmp_path, _stan(kompletnosc='trwa'))
    assert stan_sprawy.wczytaj(tmp_path)['kompletnosc'] is None


def test_komunikat_kompletnosci_jest_zachowany(tmp_path):
    stan_sprawy.zapisz(tmp_path, _stan(kompletnosc='Kompletności nie sprawdzono: brak połączenia'))
    assert stan_sprawy.wczytaj(tmp_path)['kompletnosc'].startswith('Kompletności nie sprawdzono')


def test_zapis_nie_zostawia_pliku_tymczasowego(tmp_path):
    stan_sprawy.zapisz(tmp_path, _stan())
    stan_sprawy.zapisz(tmp_path, _stan(projekt='nowa treść'))
    assert sorted(p.name for p in tmp_path.iterdir()) == ['stan.json']
    assert stan_sprawy.wczytaj(tmp_path)['projekt'] == 'nowa treść'


def test_uszkodzony_plik_jest_odkladany_na_bok(tmp_path):
    (tmp_path / 'stan.json').write_text('{ to nie jest json', 'utf-8')

    assert stan_sprawy.wczytaj(tmp_path) == {}
    nazwy = [p.name for p in tmp_path.iterdir()]
    assert 'stan.json' not in nazwy
    assert any(n.startswith('stan.json.uszkodzony-') for n in nazwy)


def test_serializacja_stabilna_bez_zmian():
    # autozapis porównuje tekst JSON – ten sam stan musi dawać ten sam wynik
    assert stan_sprawy.serializuj(_stan()) == stan_sprawy.serializuj(_stan())
