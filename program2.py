"""
Przydzielanie wniosku (.pdf / .docx / .txt / zdjęcie) do wydziałów Urzędu Miasta Bydgoszczy.

Jak to działa:
  0. Tekst: z .docx / .pdf / .txt. Gdy strona PDF nie ma tekstu (zdjęcie / skan kartki),
     albo plik jest zdjęciem (.jpg, .png ...), albo w .docx wklejono zdjęcie,
     tekst jest odczytywany lokalnie przez OCR: wbudowany OCR Windows (język polski),
     a gdy niedostępny - EasyOCR (bez internetu po pierwszym pobraniu modeli).
  1. Opisy wydziałów (zadania + rejestry) są czytane z wydzialy.md.
  2. Python liczy dopasowanie słów wniosku do zadań każdego wydziału
     (słowa kluczowe + "rdzenie" słów z wagą rzadkości) i wybiera kilku kandydatów.
     Niektóre wydziały mają WARUNEK KONIECZNY (np. WZP tylko przy zamówieniu publicznym,
     WF tylko przy finansowaniu / funduszach) - bez niego wydział jest pomijany.
  3. Bielik (LM Studio) dostaje wniosek i pełne zadania kandydatów i wybiera
     wydział(y), do których trzeba przesłać wniosek, z krótkim uzasadnieniem.
     Gdy LM Studio nie działa (albo podano --bez-llm), wynik to sam ranking.

Użycie:  py program2.py                 -> wszystkie wnioski z folderu programu
         py program2.py wniosek.pdf     -> jeden plik (pdf, docx, txt, jpg, png...)
         py program2.py C:\\folder       -> wszystkie wnioski z folderu
         py program2.py plik.pdf --bez-llm
Wymaga:  pip install pymupdf python-docx pillow winocr   (winocr: OCR na Windowsie;
         na Linux/Mac zamiast niego: pip install easyocr)
         Plik wydzialy.md w tym samym folderze. program1.py NIE jest potrzebny.
"""
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter

import pymupdf
from docx import Document

KATALOG = os.path.dirname(os.path.abspath(__file__))
LMSTUDIO_URL = "http://localhost:1235/v1/chat/completions"
MODEL = "bielik-4.5b-v3.0-instruct"
SCIEZKA_WYDZIALOW = os.path.join(KATALOG, "wydzialy.md")
ROZSZERZENIA_ZDJEC = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")
ROZSZERZENIA = (".docx", ".pdf", ".txt") + ROZSZERZENIA_ZDJEC
MIN_ZNAKOW_TEKSTU = 40        # strona PDF z mniejszą ilością tekstu = zdjęcie -> OCR
DPI_OCR = 300                 # rozdzielczość renderowania strony PDF do OCR
UZYJ_OCR_WINDOWS = True  # True = OCR Windows (zapas: EasyOCR); False = tylko EasyOCR
LICZBA_KANDYDATOW = 6         # ilu najlepszych z rankingu słów dostaje Bielik
MAKS_ZNAKOW_WNIOSKU = 3500    # tyle tekstu wniosku idzie do Bielika
MAKS_ZNAKOW_OPISU = 900       # skrót zadań jednego wydziału w zapytaniu
PROG_BEZ_LLM = 0.5          # bez Bielika: wydziały z wynikiem >= PROG * najlepszy

BEZ_OGONKOW = str.maketrans("ąćęłńóśźż", "acelnoszz")

# słowa bez znaczenia dla przydziału (pisane bez polskich znaków)
STOP = set("""
a aby albo ale ani az bez bo by byc ch co czy dla do go i ich im inne innych
jak jako je jego jej jest juz lub ma mi mnie na nad nie niz o od oraz po pod
przez przy r roku sie sa ta tak takze tam te tego tej ten to tu ul w we
z za ze zl nr dnia ktory ktora ktore ktorych wraz moj moja moje mojego
zakresie spraw sprawach prowadzenie prowadzenia zwiazanych nalezy
podstawowych zadan wydzialu miasta miasto urzedu bydgoszczy
bydgoszcz wniosek wniosku wnioskiem prosze uprzejmie zwracam pan pani panstwa
witam pozdrawiam dzien dobry informacji informacja publicznej dostepu trybie
danych dane dotyczy dotyczacy dotyczacych sprawie podanie podania szczegolnosci
""".split())

# Słowa kluczowe typowe dla wniosków mieszkańców (bez polskich znaków, początki słów).
# Każde trafienie mocno podbija wydział - to uzupełnia oficjalne opisy zadań.
SLOWA_KLUCZOWE = {
    "WAB": ["pozwoleni\\w* na budow", "warunk\\w* zabudow", "budow", "rozbudow", "przebudow",
            "zgloszeni\\w* robot", "architekt", "inicjatyw\\w* lokaln", "25/75", "lokalizacj\\w* inwestycj"],
    "WE": ["szkol", "uczni", "przedszkol", "nauczyc", "oswiat", "edukacj", "klub\\w* sportow",
           "sport", "zlobk", "uczelni", "studen"],
    "WF": ["fundusz\\w* europejsk", "unijn", "unii europejsk", "dofinansowani\\w* z ue", "strategi\\w* rozwoju",
           "raport\\w* o stanie"],
    "WGO": ["odpad", "smieci", "smietnik", "wywoz", "segregac", "dzikie wysypisk", "pojemnik", "deklaracj\\w* smieciow"],
    "WI": ["informatyk", "system\\w* teleinformatyczn", "oprogramowan", "sieci komputer", "komputer"],
    "WIM": ["inwestycj\\w* miejsk", "inwestycj", "nadzor\\w* inwestorsk", "remont\\w* budynk\\w* miejsk"],
    "WK": ["faktur", "vat", "ksiegowos", "zwrot\\w* naleznosc", "nadplat"],
    "WMG": ["nieruchomos", "dzialk", "grunt", "geodez", "ewidencj\\w* grunt", "dzierzaw", "uzytkowani\\w* wieczyst",
            "nazw\\w* ulic", "numer\\w* porzadkow", "nadani\\w* numeru", "sprzedaz\\w* lokal", "mapa", "mapy"],
    "WOS": ["srodowisk", "halas", "azbest", "zanieczyszcz", "emisj", "smog", "pieco\\w*", "studni",
            "geolog", "ocen\\w* oddzialywania", "kopciuch"],
    "WOA": ["skarg", "petycj", "interpelacj", "zarzadzeni\\w* prezydenta", "archiw", "pelnomocnictw",
            "kancelari", "rekrutacj\\w* do urzedu", "zatrudnieni\\w* w urzedzie", "infolini"],
    "WPL": ["podat", "oplat\\w* lokaln", "oplat\\w* skarbow", "ulg\\w* podatkow", "umorzeni\\w* podatk",
            "rozlozeni\\w* na raty", "interpretacj\\w* indywidualn"],
    "WSO": ["dowod\\w* osobist", "meldun", "zameldow", "wymeldow", "ewidencj\\w* ludnosc",
            "wybor(?:y|ow|ach|cz)", "referend", "alkohol", "koncesj", "rzecz\\w* znalezion", "zgub", "imprez\\w* masow",
            # stowarzyszenie/fundacja tylko jako sprawa rejestrowa - samo słowo to zwykle NADAWCA wniosku
            "zgromadzeni", "rejestr\\w* stowarzysz", "stowarzyszeni\\w* zwykl", "nadzor\\w* nad stowarzysz",
            "nadzor\\w* nad fundacj", "zalozeni\\w* stowarzysz", "repatriant", "rzecznik\\w* konsument", "ceidg",
            "dzialalnosc\\w* gospodarcz", "profil\\w* zaufan", "kwalifikacj\\w* wojskow"],
    "WSR": ["swiadczeni\\w* rodzinn", "zasilek", "zasilk", "800", "500\\+", "alimentacyjn", "fundusz\\w* alimentacyjn",
            "dodat\\w* mieszkaniow", "dodat\\w* energetyczn", "becikow", "stypendi", "za zyciem", "zasil\\w* dla opiekun",
            "pomoc\\w* materialn", "rodzin\\w* wielodzietn"],
    "WUK": ["prawo jazdy", "prawa jazdy", "rejestracj\\w* pojazd", "rejestracj\\w* samochod", "dowod\\w* rejestracyjn",
            "tablic\\w* rejestracyjn", "pojazd", "samochod", "holowan", "odholow", "parking\\w* strzezon",
            "stacj\\w* kontroli", "osrod\\w* szkolenia kierowc", "licencj\\w* na transport", "przewoz", "taxi", "taksow"],
    "WW": ["zaleglos", "egzekuc", "upomnieni", "windykac", "tytul\\w* wykonawcz", "komornik", "dlug(?!o)"],
    "WZP": ["przetarg", "zamowieni\\w* publiczn", "pzp", "ofert\\w* w postepowaniu", "specyfikacj\\w* warunkow"],
    "WZB": ["budzet", "wieloletni\\w* prognoz", "deficyt", "zadluzeni\\w* miasta", "sprawozdani\\w* budzetow"],
    "WZK": ["kryzys", "powodz", "podtopien", "obrona cywiln", "ochron\\w* ludnosc", "schron", "syren", "alarm",
            "monitoring", "kamer", "straz\\w* miejsk", "straz\\w* pozarn", "policj", "dzik", "bezdomn\\w* zwierz",
            "martw\\w* zwierz", "lowiectw", "ranne zwierz", "ochron\\w* zwierz", "odlaw", "wylapyw",
            "schronisk", "weterynar", "dokarmian", "kastracj", "sterylizacj", "czipow", "zgromadzeni\\w* w trybie uproszczonym"],
    "WGK": ["drzew", "krzew", "wycink", "ziele", "park(?:u|i|ow|iem)?\\b", "skwer", "cmentarz", "grob", "targowisk", "bazar",
            "sprzatan", "oczyszczan", "zimowe utrzymani", "meliorac", "row\\w* melioracyjn", "rybactw",
            "lokal\\w* komunaln", "mieszkani\\w* komunaln", "mieszkani\\w* socjaln", "przydzial\\w* lokal",
            "zamian\\w* mieszkani", "ochron\\w* przyrody", "pomnik\\w* przyrody"],
}

# WARUNKI KONIECZNE: wydział może być wskazany TYLKO, gdy wniosek zawiera któreś z tych słów.
# (sam opis zadań pasuje do wielu pism ogólnikowo, np. "informacja publiczna" ~ "zamówienia publiczne")
WARUNKI_KONIECZNE = {
    "WZP": ["zamowie\\w* publiczn", "przetarg", "pzp", "prawo zamowien", "inwestycj\\w* publiczn",
            "postepowani\\w* o udzielenie zamowienia", "swz", "siwz", "wykonawc", "zamawiaj","zapytani\\w* ofertow"],
    "WF": ["dofinansow", "finansowan", "fundusz", "ze srodkow", "srodk\\w* (?:z |ze )?(?:unii|ue|unijn|europejsk|zewnetrzn)",
           "unijn", "unii europejsk", "\\bue\\b", "grant", "dotacj", "program\\w* operacyjn", "kpo\\b"],
}
BONUS_SLOWA_KLUCZOWEGO = 1.0  # za każde różne trafione słowo kluczowe (ranking opisów daje 0..1)
# wniosek pytający o koszty / wydatki -> zawsze także WZB (tekst bez polskich znaków)
WZORZEC_KOSZTOW = (r"(?<![^\W\d_])(?:"
                   r"koszt|wydatk|poniesion|nakład|naklad"                       # koszty, wydatki, nakłady
                   r"|ile (?:\w+ ){0,2}wyda(?:l|lo|la|li|ly|je|ja|no)\b"          # ile miasto wydało/wydaje
                   r"|wyda(?:no|l|lo|la|li|ly|je|ja) (?:\w+ )?na\b"               # wydano na ...
                   r"|wydan\w* (?:srodk|kwot|pieniadz)|kwot"                     # kwota, wydane środki
                   r"|cen(?:a|y|e|ach|ami|om|ow)?\b|cenow|ile kosztuj"        # cena, ceny, cenowy
                   r"|srodk\w* (?:finansow|publiczn|budzetow|pienie)"             # środki finansowe/publiczne
                   r"|przeznacz\w* (?:\w+ ){0,3}(?:srodk|kwot|pieniadz|na\b)"     # przeznaczone środki / przeznaczono na
                   r"|srodk\w* przeznacz|finansowan|dofinansow|dotacj|sfinansow"  # (do)finansowanie, dotacje
                   r"|faktur|platnosc|zaplac|przelew|wynagrodzeni"               # faktury, płatności, przelewy
                   r"|wartosc\w* (?:umow|zamowien|kontrakt|zlecen|inwestycj|projekt|prac|robot)"
                   r"|budzet)")
MIN_SLOW_KLUCZOWYCH_LIDERA = 2  # lider rankingu z tyloma słowami kluczowymi zawsze jest w "PRZEŚLIJ DO"


def bez_ogonkow(tekst):
    return tekst.lower().translate(BEZ_OGONKOW)


def rdzen(slowo):
    """Bardzo prosty 'stemmer': pierwsze 5 liter bez polskich znaków (szkół/szkołach -> szkol)."""
    return slowo[:5]


def rdzenie(tekst):
    slowa = re.findall(r"[^\W\d_]{3,}", bez_ogonkow(tekst))
    return [rdzen(s) for s in slowa if s not in STOP]


def trafienia_slow_kluczowych(tekst):
    """{skrót wydziału: [trafione słowa kluczowe]}"""
    tekst = bez_ogonkow(tekst)
    wynik = {}
    for skrot, slowa in SLOWA_KLUCZOWE.items():
        trafione = [s.replace("\\w*", "").replace("\\", "") for s in slowa
                    if re.search(r"(?<![^\W\d_])" + bez_ogonkow(s), tekst)]
        if trafione:
            wynik[skrot] = trafione
    return wynik


def spelnia_warunek(skrot, tekst):
    """True, jeśli wydział nie ma warunku koniecznego albo wniosek go spełnia."""
    warunki = WARUNKI_KONIECZNE.get(skrot)
    if not warunki:
        return True
    tekst = bez_ogonkow(tekst)
    return any(re.search(r"(?<![^\W\d_])" + w, tekst) for w in warunki)


# --- 0. Odczyt tekstu (z OCR dla zdjęć) --------------------------------------
def wczytaj_akapity(sciezka):
    s = sciezka.lower()
    if s.endswith(".docx"):
        return [p.text for p in Document(sciezka).paragraphs if p.text.strip()]
    if s.endswith(".pdf"):
        with pymupdf.open(sciezka) as pdf:
            tekst = "\n".join(strona.get_text() for strona in pdf)
        return [l for l in tekst.splitlines() if l.strip()]
    if s.endswith(".txt"):
        with open(sciezka, encoding="utf-8") as f:
            return [l for l in f.read().splitlines() if l.strip()]
    raise ValueError(f"Nieobsługiwany format pliku: {sciezka}")


_czytnik_ocr = None
_winocr_dziala = None   # None = jeszcze nie sprawdzano


def ocr_windows(obraz):
    """OCR wbudowanym silnikiem Windows (język polski, bez pobierania modeli).
    Zwraca tekst albo None, gdy OCR Windows jest niedostępny."""
    global _winocr_dziala
    if _winocr_dziala is False:
        return None
    try:
        import io
        import winocr
        from PIL import Image
        img = Image.open(obraz if isinstance(obraz, str) else io.BytesIO(obraz))
        img = img.convert("RGBA")
        # silnik Windows ma limit rozmiaru obrazu - zmniejsz za duże zdjęcia
        if max(img.size) > 9000:
            img.thumbnail((9000, 9000))
        wynik = winocr.recognize_pil_sync(img, lang="pl")
        _winocr_dziala = True
        return "\n".join(linia["text"] for linia in wynik["lines"])
    except Exception as e:
        if _winocr_dziala is None:
            print(f"  (OCR Windows niedostępny: {e} - używam EasyOCR)")
        _winocr_dziala = False
        return None


def ocr(obraz):
    """OCR obrazu (ścieżka albo bajty PNG/JPG) -> tekst. Działa lokalnie:
    najpierw OCR Windows, a gdy niedostępny - EasyOCR."""
    if UZYJ_OCR_WINDOWS:
        tekst = ocr_windows(obraz)
        if tekst is not None:
            return tekst
    global _czytnik_ocr
    if _czytnik_ocr is None:
        try:
            import easyocr
        except ImportError:
            raise RuntimeError("Do odczytu zdjęć potrzebny jest EasyOCR: py -m pip install easyocr")
        print("  (OCR: ładuję model EasyOCR - pierwsze uruchomienie pobiera go jednorazowo)")
        _czytnik_ocr = easyocr.Reader(["pl", "en"], gpu=False, verbose=False)
    wyniki = _czytnik_ocr.readtext(obraz, detail=1, paragraph=False)
    return poskladaj_linie(wyniki)


MIN_PEWNOSC_OCR = 0.25   # fragmenty EasyOCR o niższej pewności (pieczątki, bazgroły) są pomijane


def poskladaj_linie(wyniki):
    """Składa fragmenty z EasyOCR [(ramka, tekst, pewność)] w linie tekstu w kolejności czytania.
    (paragraph=True w EasyOCR miesza kolumny i sąsiednie linie.)"""
    fragmenty = []
    for ramka, tekst, pewnosc in wyniki:
        if pewnosc < MIN_PEWNOSC_OCR or not tekst.strip():
            continue
        ys = [p[1] for p in ramka]
        xs = [p[0] for p in ramka]
        fragmenty.append({"y": (min(ys) + max(ys)) / 2, "h": max(ys) - min(ys),
                          "x": min(xs), "tekst": tekst.strip()})
    fragmenty.sort(key=lambda f: f["y"])

    linie = []   # fragment należy do linii, gdy jego środek leży w połowie wysokości tej linii
    for f in fragmenty:
        if linie and abs(f["y"] - linie[-1]["y"]) < 0.5 * max(f["h"], linie[-1]["h"]):
            linie[-1]["czesci"].append(f)
        else:
            linie.append({"y": f["y"], "h": f["h"], "czesci": [f]})

    wynik = []
    for linia in linie:
        tekst = " ".join(f["tekst"] for f in sorted(linia["czesci"], key=lambda f: f["x"]))
        # EasyOCR często czyta samotne "o" jako "0" ("wniosek 0 udostępnienie")
        # (tylko samotne "0" bez cyfr obok i nie przed jednostką, żeby nie psuć "0 zł", "10 0")
        tekst = re.sub(r"(?<!\S)(?<![\d.,]\s)0(?!\S)(?!\s*(?:\d|zł|zl|pln|gr|%))", "o", tekst,
                       flags=re.IGNORECASE)
        wynik.append(tekst)
    return "\n".join(wynik)


def wczytaj_tekst(sciezka):
    """Tekst wniosku z dowolnego obsługiwanego pliku; zdjęcia i skany przez OCR."""
    s = sciezka.lower()
    if s.endswith(ROZSZERZENIA_ZDJEC):
        print("  OCR zdjęcia...")
        return ocr(sciezka)

    if s.endswith(".pdf"):
        czesci = []
        with pymupdf.open(sciezka) as pdf:
            for nr, strona in enumerate(pdf, 1):
                tekst = strona.get_text()
                if len(tekst.strip()) < MIN_ZNAKOW_TEKSTU:  # brak warstwy tekstowej = zdjęcie kartki
                    print(f"  OCR strony {nr} (brak tekstu - zdjęcie/skan)...")
                    tekst = ocr(strona.get_pixmap(dpi=DPI_OCR).tobytes("png"))
                czesci.append(tekst)
        return "\n".join(czesci)

    tekst = "\n".join(wczytaj_akapity(sciezka))
    if s.endswith(".docx") and len(tekst.strip()) < MIN_ZNAKOW_TEKSTU:
        # Word z wklejonym zdjęciem kartki
        doc = Document(sciezka)
        obrazy = [p.blob for p in doc.part.related_parts.values()
                  if p.content_type.startswith("image/")]
        for nr, blob in enumerate(obrazy, 1):
            print(f"  OCR zdjęcia {nr}/{len(obrazy)} z dokumentu Word...")
            tekst += "\n" + ocr(blob)
    return tekst


def pliki_w_folderze(folder):
    """Wnioski w folderze: bez wyników program1 (_oznaczony) i plików tymczasowych Worda (~$)."""
    return [os.path.join(folder, n) for n in sorted(os.listdir(folder))
            if n.lower().endswith(ROZSZERZENIA)
            and not os.path.splitext(n)[0].endswith("_oznaczony")
            and not n.startswith("~$")]


# --- 1. Wydziały z wydzialy.md -----------------------------------------------
def wczytaj_wydzialy(sciezka):
    """Zwraca listę słowników: nazwa, skrot, zadania (tekst), rejestry (tekst)."""
    with open(sciezka, encoding="utf-8") as f:
        tresc = f.read()
    wydzialy = []
    for blok in re.split(r"^## ", tresc, flags=re.M)[1:]:
        naglowek, _, reszta = blok.partition("\n")
        m = re.match(r"(.+?)\s*\((\S+)\)\s*$", naglowek.strip())
        if not m:
            continue
        sekcje = re.split(r"^### ", reszta, flags=re.M)
        zadania = next((s.partition("\n")[2] for s in sekcje if s.startswith("Zadania")), "")
        rejestry = next((s.partition("\n")[2] for s in sekcje if s.startswith("Nazwy")), "")
        czysc = lambda t: re.sub(r"https?://\S+|^---$", "", t, flags=re.M).strip()
        wydzialy.append({"nazwa": m.group(1), "skrot": m.group(2),
                         "zadania": czysc(zadania), "rejestry": czysc(rejestry)})
    if not wydzialy:
        sys.exit(f"Nie znalazłem wydziałów w {sciezka}")
    return wydzialy


# --- 2. Ranking słów ---------------------------------------------------------
def ranking(tekst_wniosku, wydzialy):
    """Wynik każdego wydziału = suma wag IDF rdzeni wspólnych z wnioskiem.
    Rzadkie słowa (np. 'drzew', 'alkohol', 'prawo jazdy') ważą dużo, częste mało."""
    zbiory = []
    for w in wydzialy:
        # nazwa wydziału liczy się podwójnie
        zbiory.append(Counter(rdzenie(w["nazwa"]) * 2 + rdzenie(w["zadania"] + " " + w["rejestry"])))
    n = len(wydzialy)
    idf = {}
    for z in zbiory:
        for r in z:
            idf[r] = idf.get(r, 0) + 1
    idf = {r: math.log((n + 1) / c) for r, c in idf.items()}

    wniosek = Counter(rdzenie(tekst_wniosku))
    surowe = []
    for w, z in zip(wydzialy, zbiory):
        wspolne = [r for r in wniosek if r in z]
        # log - słowo powtórzone 10 razy nie zdominuje wyniku
        punkty = sum(idf[r] * (1 + math.log(wniosek[r])) * (1 + math.log(z[r])) for r in wspolne)
        punkty /= math.sqrt(sum(z.values()))  # długie opisy nie mają przewagi
        surowe.append((punkty, w, sorted(wspolne, key=lambda r: -idf[r] * wniosek[r])[:4]))

    # wynik = trafienia słów kluczowych + ranking opisów znormalizowany do 0..1
    maks = max(p for p, _, _ in surowe) or 1
    kluczowe = trafienia_slow_kluczowych(tekst_wniosku)
    wyniki = []
    for punkty, w, top in surowe:
        if not spelnia_warunek(w["skrot"], tekst_wniosku):
            continue  # np. WZP bez słowa o zamówieniu publicznym
        trafione = kluczowe.get(w["skrot"], [])
        wyniki.append((len(trafione) * BONUS_SLOWA_KLUCZOWEGO + punkty / maks, w, trafione + top))
    wyniki.sort(key=lambda x: -x[0])
    return wyniki


# --- 3. Bielik wybiera spośród kandydatów -----------------------------------
def wyslij(instrukcja, polecenie):
    """Zapytanie do Bielika w LM Studio -> słownik z JSON-a odpowiedzi ({} gdy brak JSON-a)."""
    zapytanie = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": instrukcja},
            {"role": "user", "content": polecenie},
        ],
        "temperature": 0.0,
        "max_tokens": 700,  # limit długości odpowiedzi - generowanie to najwolniejsza część
        # uwaga: "response_format" (json_schema) w LM Studio wywala się na tokenizerze Bielika,
        # więc JSON wyciągamy z odpowiedzi tekstowej
    }
    req = urllib.request.Request(
        LMSTUDIO_URL,
        data=json.dumps(zapytanie).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as odp:
        wynik = json.loads(odp.read().decode("utf-8"))
    tresc = wynik["choices"][0]["message"]["content"]
    for kandydat in (tresc, *re.findall(r"\{.*\}", tresc, re.DOTALL)):
        try:
            obiekt = json.loads(kandydat)
            return obiekt if isinstance(obiekt, dict) else {}
        except json.JSONDecodeError:
            pass
    return {}  # model nie zwrócił poprawnego JSON-a



SYSTEM = ("Jesteś pracownikiem kancelarii Urzędu Miasta Bydgoszczy. Na podstawie treści "
          "wniosku wskazujesz wydziały właściwe do jego załatwienia. Odpowiadasz wyłącznie JSON-em.")


def skrot_zadan(zadania, tekst_wniosku):
    """Skrót zadań wydziału do MAKS_ZNAKOW_OPISU znaków: najpierw zadania najbardziej
    pasujące do wniosku (żeby np. punkt 7 WZK o zwierzętach nie był odcinany), potem reszta
    w oryginalnej kolejności."""
    punkty = [" ".join(p.split()) for p in re.split(r"\n\s*(?=\d+\.\s)", zadania) if p.strip()]
    slowa_wniosku = set(rdzenie(tekst_wniosku))
    dopasowanie = [len(set(rdzenie(p)) & slowa_wniosku) for p in punkty]
    kolejnosc = sorted(range(len(punkty)), key=lambda i: (-dopasowanie[i], i))
    opis = ""
    for i in kolejnosc:
        if len(opis) + len(punkty[i]) + 1 > MAKS_ZNAKOW_OPISU:
            if not opis:  # pierwsze zadanie samo za długie - przytnij je
                opis = punkty[i][:MAKS_ZNAKOW_OPISU].rsplit(" ", 1)[0]
            return opis + " ..."
        opis += (" " if opis else "") + punkty[i]
    return opis


def polecenie(tekst_wniosku, kandydaci):
    opisy = []
    for w in kandydaci:
        opis = skrot_zadan(w["zadania"], tekst_wniosku)
        opisy.append(f"[{w['skrot']}] {w['nazwa']}: {opis}")
    return (
        "WYDZIAŁY (skrót w nawiasie kwadratowym; uporządkowane od najbardziej "
        "prawdopodobnego wg słów kluczowych):\n" + "\n\n".join(opisy) +
        "\n\nPrzeczytaj WNIOSEK i wybierz wydział lub wydziały, do których należy go przesłać. "
        "Wybierz kilka tylko wtedy, gdy wniosek naprawdę dotyczy spraw kilku wydziałów "
        "(np. różnych próśb w jednym piśmie). Wybieraj wyłącznie spośród powyższych skrótów.\n"
        'Zwróć WYŁĄCZNIE JSON: {"wydzialy": [{"skrot": "...", "uzasadnienie": "krótko, czego dotyczy"}]}\n\n'
        "WNIOSEK:\n" + tekst_wniosku[:MAKS_ZNAKOW_WNIOSKU]
    )


def wybierz_llm(tekst_wniosku, kandydaci):
    odp = wyslij(SYSTEM, polecenie(tekst_wniosku, kandydaci))
    po_skrocie = {w["skrot"].upper(): w for w in kandydaci}
    wynik = []
    for d in odp.get("wydzialy", []) if isinstance(odp.get("wydzialy"), list) else []:
        if not isinstance(d, dict):
            continue
        skrot = str(d.get("skrot", "")).strip(" []()").upper()
        if skrot in po_skrocie and po_skrocie[skrot] not in [w for w, _ in wynik]:
            wynik.append((po_skrocie[skrot], str(d.get("uzasadnienie", "")).strip()))
    return wynik


# --- 4. Program --------------------------------------------------------------
def przydziel(plik, wydzialy, uzyj_llm=True):
    tekst = wczytaj_tekst(plik)
    if not tekst.strip():
        print("Brak tekstu w pliku (skan bez warstwy tekstowej?)")
        return

    wyniki = ranking(tekst, wydzialy)
    print("Ranking (punkty: 1 za każde słowo kluczowe + 0..1 za podobieństwo do opisu zadań):")
    for punkty, w, top in wyniki[:LICZBA_KANDYDATOW]:
        print(f"  {punkty:6.2f}  {w['skrot']:5} {w['nazwa']}  ({', '.join(top)})")

    # pytania o koszty / wydatki zawsze idą także do Wydziału Zarządzania Budżetem Miasta
    wzb = None
    if re.search(WZORZEC_KOSZTOW, bez_ogonkow(tekst)):
        wzb = next((w for w in wydzialy if w["skrot"] == "WZB"), None)

    if uzyj_llm:
        try:
            wybor = wybierz_llm(tekst, [w for _, w, _ in wyniki[:LICZBA_KANDYDATOW]])
            # zabezpieczenie: mały model potrafi pominąć oczywistego lidera rankingu
            lider = wyniki[0][1]
            trafione = trafienia_slow_kluczowych(tekst).get(lider["skrot"], [])
            if wybor and len(trafione) >= MIN_SLOW_KLUCZOWYCH_LIDERA \
                    and lider not in [w for w, _ in wybor]:
                wybor.insert(0, (lider, "z rankingu słów (pominięty przez Bielika), pasujące: "
                                        + ", ".join(trafione)))
            if wybor and wzb and wzb not in [w for w, _ in wybor]:
                wybor.append((wzb, "pytanie o poniesione koszty / wydatki"))
            if wybor:
                print("\nPRZEŚLIJ DO:")
                for w, uzas in wybor:
                    print(f"  -> {w['nazwa']} ({w['skrot']})" + (f": {uzas}" if uzas else ""))
                return
            print("\nBielik nie zwrócił poprawnej odpowiedzi - wynik z rankingu słów.")
        except urllib.error.URLError as e:
            print(f"\nBrak połączenia z LM Studio ({LMSTUDIO_URL}: {e}) - wynik z rankingu słów.")

    najlepszy = wyniki[0][0]
    if najlepszy <= 0:
        print("\nNie udało się dopasować wniosku do żadnego wydziału.")
        return
    print("\nPRZEŚLIJ DO (ranking słów):")
    wybrane = [(w, top) for punkty, w, top in wyniki if punkty >= PROG_BEZ_LLM * najlepszy]
    for w, top in wybrane:
        print(f"  -> {w['nazwa']} ({w['skrot']})  [pasujące: {', '.join(top)}]")
    if wzb and wzb not in [w for w, _ in wybrane]:
        print(f"  -> {wzb['nazwa']} ({wzb['skrot']})  [pytanie o poniesione koszty / wydatki]")


def main():
    argumenty = [a for a in sys.argv[1:] if not a.startswith("--")]
    uzyj_llm = "--bez-llm" not in sys.argv
    cel = argumenty[0] if argumenty else KATALOG
    if os.path.isdir(cel):
        pliki = pliki_w_folderze(cel)
    elif os.path.exists(cel):
        pliki = [cel]
    else:
        sys.exit(f"Nie ma takiego pliku ani folderu: {cel}")
    if not pliki:
        sys.exit(f"Brak wniosków ({', '.join(ROZSZERZENIA)}) w: {cel}")

    wydzialy = wczytaj_wydzialy(SCIEZKA_WYDZIALOW)
    for nr, plik in enumerate(pliki, 1):
        print(f"===== [{nr}/{len(pliki)}] {os.path.basename(plik)} =====")
        try:
            przydziel(plik, wydzialy, uzyj_llm)
        except Exception as e:
            print(f"POMINIĘTO - błąd: {e}")
        print()


if __name__ == "__main__":
    main()
