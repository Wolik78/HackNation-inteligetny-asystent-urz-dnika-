"""Testy klienta Bielika na podstawionym serwerze (bez prawdziwego LM Studio)."""

import asyncio
import json

import httpx
import pytest

from asystent.ai import BielikService, BladAI
from asystent.ai.bielik_service import (dopasuj_w_tekscie, fragment_w_tekscie, podziel_tekst, przytnij_do_budzetu,
                                        usun_markdown, wyciagnij_json)

URL = 'http://lm-studio.test/v1'
MODEL = 'bielik-test'


def odpowiedz_czatu(tresc: str) -> httpx.Response:
    return httpx.Response(200, json={'choices': [{'message': {'content': tresc}}]})


def serwis(obsluga, kontekst: int | None = 3072, **kwargs) -> BielikService:
    """BielikService z podstawionym serwerem. `obsluga(request, payload)` odpowiada na /chat/completions."""
    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/models'):
            return httpx.Response(200, json={'data': [{'id': MODEL}]})
        if '/api/v0/models/' in request.url.path:
            if kontekst is None:
                return httpx.Response(404)
            return httpx.Response(200, json={'loaded_context_length': kontekst})
        return obsluga(request, json.loads(request.content))
    return BielikService(URL, MODEL, transport=httpx.MockTransport(transport), **kwargs)


def uruchom(korutyna):
    return asyncio.run(korutyna)


# --- analiza wniosku ---

def test_analiza_wniosku_parsuje_json_w_bloku_kodu():
    tresc = '```json\n{"skrocony_opis": "Wydatki na promocję", "sugerowane_wydzialy": ["Wydział Promocji"],' \
            ' "uzasadnienie_wydzialu": "Odpowiada za promocję.", "czy_wymaga_kwerendy": false}\n```'
    wynik = uruchom(serwis(lambda r, p: odpowiedz_czatu(tresc)).analizuj_wniosek('wniosek'))

    assert wynik.skrocony_opis == 'Wydatki na promocję'
    assert wynik.sugerowane_wydzialy == ['Wydział Promocji']
    assert wynik.czy_wymaga_kwerendy is False


def test_analiza_toleruje_typy_od_malego_modelu():
    tresc = '{"skrocony_opis": "X", "sugerowane_wydzialy": "Wydział Finansów", "czy_wymaga_kwerendy": "tak"}'
    wynik = uruchom(serwis(lambda r, p: odpowiedz_czatu(tresc)).analizuj_wniosek('wniosek'))

    assert wynik.sugerowane_wydzialy == ['Wydział Finansów']
    assert wynik.czy_wymaga_kwerendy is True
    assert wynik.uzasadnienie_wydzialu == ''


def test_wysylany_jest_model_temperatura_i_przyciety_tekst():
    wyslane = {}

    def obsluga(request, payload):
        wyslane.update(payload)
        return odpowiedz_czatu('{"skrocony_opis": "X"}')

    uruchom(serwis(obsluga, limit_znakow=6000).analizuj_wniosek('a' * 20_000))

    assert wyslane['model'] == MODEL
    assert wyslane['temperature'] == 0.1
    assert wyslane['stream'] is False
    assert wyslane['messages'][1]['content'].count('a') == 6000


def test_limit_znakow_dopasowuje_sie_do_malego_okna_kontekstu():
    wyslane = {}

    def obsluga(request, payload):
        wyslane.update(payload)
        return odpowiedz_czatu('{"skrocony_opis": "X"}')

    uruchom(serwis(obsluga, kontekst=2048).analizuj_wniosek('a' * 20_000))
    assert wyslane['messages'][1]['content'].count('a') < 4000


def test_niepoprawny_json_daje_czytelny_blad():
    with pytest.raises(BladAI, match='niepoprawnym formacie'):
        uruchom(serwis(lambda r, p: odpowiedz_czatu('Nie wiem, co odpowiedzieć.')).analizuj_wniosek('w'))


# --- błędy połączenia ---

def test_wylaczone_lm_studio():
    def brak_serwera(request):
        raise httpx.ConnectError('Connection refused', request=request)

    bielik = BielikService(URL, MODEL, transport=httpx.MockTransport(brak_serwera))
    with pytest.raises(BladAI, match='Brak połączenia'):
        uruchom(bielik.analizuj_wniosek('wniosek'))
    status = uruchom(bielik.status())
    assert not status.dostepny and 'nie odpowiada' in status.komunikat


def test_przekroczony_czas():
    def wolny_serwer(request, payload):
        raise httpx.ReadTimeout('timeout', request=request)

    with pytest.raises(BladAI, match='nie odpowiedział'):
        uruchom(serwis(wolny_serwer).analizuj_wniosek('wniosek'))


def test_blad_serwera_jest_przekazany():
    blad = httpx.Response(400, json={'error': 'Model is not loaded'})
    with pytest.raises(BladAI, match='Model is not loaded'):
        uruchom(serwis(lambda r, p: blad).analizuj_wniosek('wniosek'))


def test_status_gotowego_modelu():
    status = uruchom(serwis(lambda r, p: odpowiedz_czatu('')).status())
    assert status.dostepny and status.kontekst == 3072


# --- dane osobowe ---

def test_dane_osobowe_tylko_te_ktore_sa_w_tekscie():
    tekst = 'Wniosek złożył Jan Kowalski, tel. 601 234 567. Odpowiada Prezydent Miasta.'
    tresc = '{"do_ukrycia": ["Jan Kowalski", "601 234 567", "Janina Kowalska", "Jan Kowalski"]}'
    wynik = uruchom(serwis(lambda r, p: odpowiedz_czatu(tresc)).wykryj_dane_osobowe(tekst))

    assert wynik == ['Jan Kowalski', '601 234 567']  # zmyślona „Janina” i duplikat odrzucone


def test_dane_osobowe_w_innej_formie_fleksyjnej():
    tekst = 'Szanowny Panie Janie Testowy, odpowiadam na wniosek z 20.11.2026 r.\nZ poważaniem dla Jana Testowego'
    tresc = '{"do_ukrycia": ["Jan Testowy", "20.11.2026", "1 240 000 zł"]}'
    wynik = uruchom(serwis(lambda r, p: odpowiedz_czatu(tresc)).wykryj_dane_osobowe(tekst))

    assert wynik == ['Janie Testowy', 'Jana Testowego']  # data i kwota odrzucone


def test_dopasuj_w_tekscie():
    assert dopasuj_w_tekscie('Anna Nowak-Kowalska', 'Pani Annie Nowak-Kowalskiej') == ['Annie Nowak-Kowalskiej']
    assert dopasuj_w_tekscie('601 234 567', 'tel. 601 234 567') == ['601 234 567']
    assert dopasuj_w_tekscie('601234567', 'tel. 601 234 567') == []  # liczby tylko dosłownie
    assert dopasuj_w_tekscie('Janina Kowalska', 'Jan Kowalski') == []


def test_usun_markdown():
    tekst = '**ODPOWIEDŹ**\n\n### **Podstawa prawna:**\nKwota: **740 000 zł**\n---\nZ poważaniem'
    assert usun_markdown(tekst) == 'ODPOWIEDŹ\n\nPodstawa prawna:\nKwota: 740 000 zł\n\nZ poważaniem'


def test_dlugi_tekst_jest_sprawdzany_w_czesciach():
    zapytania = []

    def obsluga(request, payload):
        zapytania.append(payload)
        return odpowiedz_czatu('{"do_ukrycia": []}')

    tekst = ('Akapit z treścią. ' * 50 + '\n\n') * 20  # ~18 000 znaków
    uruchom(serwis(obsluga).wykryj_dane_osobowe(tekst))
    assert len(zapytania) >= 3


# --- kompletność ---

PROJEKT = 'Uprzejmie informuję, że w 2025 roku wydano łącznie 1 240 000 zł. Kampania „Bydgoszcz nad wodą” – 740 000 zł.'


def test_kompletnosc_wymaga_dowodu_z_projektu():
    tresc = json.dumps({'zadania': [
        {'zadanie': 'ile wydano w 2025', 'odpowiedziano': True, 'fragment': 'w 2025 roku wydano łącznie 1 240 000 zł'},
        {'zadanie': 'podział na kampanie', 'odpowiedziano': True,
         'fragment': 'Kampania "Bydgoszcz nad wodą" - 740 000 zł'},          # inne cudzysłowy i myślnik
        {'zadanie': 'kopie umów', 'odpowiedziano': True, 'fragment': ''},       # „tak” bez dowodu
        {'zadanie': 'nazwy wykonawców', 'odpowiedziano': True, 'fragment': 'wykonawcą była Agencja Fala'},  # zmyślony
    ]}, ensure_ascii=False)
    wynik = uruchom(serwis(lambda r, p: odpowiedz_czatu(tresc)).sprawdz_kompletnosc('wniosek', PROJEKT))

    assert [(z.tresc, z.odpowiedziano) for z in wynik] == [
        ('ile wydano w 2025', True), ('podział na kampanie', True), ('kopie umów', False), ('nazwy wykonawców', False)]


def test_kompletnosc_bez_zadan_to_blad():
    with pytest.raises(BladAI):
        uruchom(serwis(lambda r, p: odpowiedz_czatu('{"zadania": []}')).sprawdz_kompletnosc('w', PROJEKT))


def test_fragment_w_tekscie():
    assert fragment_w_tekscie('wydano łącznie 1 240 000 zł', PROJEKT)
    assert not fragment_w_tekscie('', PROJEKT)
    assert not fragment_w_tekscie('umowy zostały załączone do pisma', PROJEKT)


# --- generowanie (stream) ---

def test_generowanie_strumieniowe():
    linie = [
        {'choices': [{'delta': {'role': 'assistant'}}]},
        {'choices': [{'delta': {'content': 'Szanowny '}}]},
        {'choices': [{'delta': {'content': 'Panie,'}}]},
    ]
    cialo = ''.join(f'data: {json.dumps(l)}\n\n' for l in linie) + 'data: nie-json\n\ndata: [DONE]\n\n'
    wyslane = {}

    def obsluga(request, payload):
        wyslane.update(payload)
        return httpx.Response(200, content=cialo.encode(), headers={'content-type': 'text/event-stream'})

    async def zbierz():
        return ''.join([k async for k in serwis(obsluga).generuj_odpowiedz(
            wniosek='wniosek', informacje_wydzialow='1 240 000 zł')])

    assert uruchom(zbierz()) == 'Szanowny Panie,'
    assert wyslane['stream'] is True
    assert '1 240 000 zł' in wyslane['messages'][1]['content']


def test_generowanie_bez_serwera():
    def brak_serwera(request):
        raise httpx.ConnectError('Connection refused', request=request)

    async def zbierz():
        bielik = BielikService(URL, MODEL, transport=httpx.MockTransport(brak_serwera))
        return [k async for k in bielik.generuj_odpowiedz(wniosek='w', informacje_wydzialow='i')]

    with pytest.raises(BladAI, match='Brak połączenia'):
        uruchom(zbierz())


# --- funkcje pomocnicze ---

def test_wyciagnij_json_z_tekstem_dookola_i_przecinkiem():
    assert wyciagnij_json('Oto wynik: {"a": [1, 2,],} Dziękuję.') == {'a': [1, 2]}


def test_podziel_tekst_na_granicy_akapitu():
    czesci = podziel_tekst('Pierwszy akapit.\n\nDrugi akapit, dłuższy od limitu.', 30)
    assert czesci[0] == 'Pierwszy akapit.'
    assert all(len(c) <= 30 for c in czesci)


def test_przytnij_do_budzetu():
    wniosek, informacje, wzor = przytnij_do_budzetu(1000, 'w' * 900, 'i' * 900, 'z' * 900)
    assert len(wniosek) + len(informacje) + len(wzor) <= 1000
    assert len(informacje) > len(wniosek) > len(wzor)
