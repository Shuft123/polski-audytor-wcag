# AI: analiza wizyjna i fokus – sprint 1

Notatka ze sprintu 1. Osoba 4: Miłosz Michalski. Funkcjonalności: F8 (test fokusu), przygotowanie pod F13 (kontrast na obrazach) i pod `obraz_opis` w F9.

Zakres z planu sprintu:
1. wybór i test modelu wizyjnego na ok. 10 zrzutach ekranu,
2. prototyp przechodzenia stroną klawiszem Tab z zapisem zrzutu aktywnego elementu,
3. wstępna decyzja, jak mierzyć widoczność fokusu i kontrast na obrazach.

Pliki:
- moduł testu fokusu: [`src/audytor/fokus/`](../src/audytor/fokus/) (`tab.py` – przeglądarka, `pomiar.py` – porównanie zrzutów, `cli.py`),
- testy: [`tests/fokus/`](../tests/fokus/) (pomiar bez przeglądarki + 3 strony testowe w Chromium),
- test modelu wizyjnego: [`scripts/test_modelu_wizyjnego.py`](../scripts/test_modelu_wizyjnego.py).

## 1. Test fokusu (F8, WCAG 2.4.7)

### Uruchomienie
```powershell
python -m audytor.fokus https://pb.edu.pl/                    # albo: audytor-fokus https://pb.edu.pl/
python -m audytor.fokus https://www.gov.pl/ --max-krokow 40 --out wyniki/fokus
```
Wynik w `wyniki/fokus/<strona>/` (folder jest w `.gitignore`):
- `fokus.json` – kroki w kolejności Tab, pomiary, problemy w formacie wspólnego modelu wyniku,
- `kroki/NN_porownanie.png` – obraz [bez fokusu | z fokusem | zmienione piksele na czerwono],
- `mapa-fokusu.png` – zrzut całej strony z ponumerowaną kolejnością Tab (kolor ramki = werdykt). Przyda się też do oceny kolejności fokusu (2.4.3) przez człowieka albo model wizyjny.

Z innych modułów (na tej samej otwartej stronie co crawler i axe-core, zgodnie z kontraktem danych, sekcja 1.5):
```python
from audytor.crawler import Renderer
from audytor.fokus import przejdz_tabem

with Renderer() as renderer:
    with renderer.open("https://pb.edu.pl/") as opened:
        wynik_fokusu = przejdz_tabem(opened.page, url=opened.final_url, max_krokow=60)
        wynik_fokusu.problemy   # lista słowników w formacie audytor.wyniki.Problem (F7)
```

### Jak mierzymy widoczność fokusu (decyzja wstępna)
Dla każdego naciśnięcia Tab:
1. odczytujemy aktywny element (`document.activeElement`, także w shadow DOM): selektor, rola, nazwa, położenie, styl `outline`/`box-shadow`,
2. robimy zrzut obszaru elementu + 10 px marginesu **z fokusem**,
3. zdejmujemy fokus (`blur()`), robimy zrzut **tego samego obszaru bez fokusu** i oddajemy fokus,
4. porównujemy zrzuty piksel po pikselu:
   - **zmienione piksele** – różnica kanału > 24 (odsiewa antyaliasing),
   - **kontrastowe piksele** – zmiana koloru o kontraście ≥ 3:1 (wzór WCAG na kontrast; próg 3:1 bierzemy z WCAG 2.2, kryteria 2.4.11/2.4.13, bo 2.4.7 w WCAG 2.1 nie podaje liczby),
   - **wskaźnik** = kontrastowe piksele / obwód elementu. Wskaźnik 1,0 ≈ jednopikselowa, kontrastowa ramka dookoła.

Dlaczego zrzuty, a nie odczyt CSS: styl `outline` w CSS nie mówi, czy obwódkę widać. Na pb.edu.pl pole „Szukaj” ma `outline: 3px solid`, ale w kolorze tła nagłówka. Z kolei kafelki slajdera mają obwódkę ucinaną przez `overflow: hidden` rodzica. Oba przypadki wykrywa dopiero porównanie zrzutów.

| Werdykt | Warunek | Problem w wyniku | Pewność |
|---|---|---|---|
| `ok` | wskaźnik ≥ 1,0 | – | – |
| `slaby` | jest zmiana, ale wskaźnik < 1,0 | `fokus-slabo-widoczny` (2.4.7, umiarkowana) | 0,6 |
| `brak` | żaden piksel się nie zmienił | `fokus-niewidoczny` (2.4.7, poważna) | 0,9 |
| `niewidoczny` | element ma zerowy rozmiar albo leży poza ekranem | `fokus-poza-ekranem` (2.4.7, umiarkowana) | 0,5 |
| `zgubiony` | Tab przeniósł fokus na `<body>`, a następny Tab wrócił na stronę | `fokus-zgubiony` (2.4.7, poważna) | 0,7 |
| – | 3 kolejne Taby na tym samym elemencie | `fokus-pulapka` (2.1.2, krytyczna) | 0,7 |

Wszystkie problemy mają status `do_weryfikacji` – zgodnie z założeniem projektu wynik heurystyki/AI ocenia człowiek.

### Wyniki na żywych stronach (13.11.2026, pierwsze 40 elementów)
| Strona | Widoczny | Słaby | Brak | Poza ekranem | Zgubiony |
|---|---|---|---|---|---|
| pb.edu.pl | 26 | 10 | 4 | 0 | 0 |
| gov.pl | 40 | 0 | 0 | 0 | 0 |
| bialystok.pl | 23 | 7 | 9 | 1 | 0 |
| wasilkow.pl | 5 | 15 | 15 | 0 | 5 |

Sprawdzone ręcznie na obrazach porównania:
- pb.edu.pl, pole „Szukaj” – `brak`: obwódka w kolorze tła, prawdziwy problem,
- pb.edu.pl, kafelek slajdera – `brak`: obwódka ucięta przez kontener, prawdziwy problem,
- wasilkow.pl, przyciski zmiany czcionki – `slaby`: cienka, jasnoniebieska ramka na białym tle,
- wasilkow.pl, menu główne – `zgubiony`: Tab z pozycji menu wchodzi w ukryte podmenu i fokus znika.

Czas: ok. 0,9 s na element (dwa zrzuty + pauzy na animacje) plus renderowanie strony; 30 elementów na pb.edu.pl razem z renderowaniem trwało 35 s. Do sprintu 4 warto przyspieszyć (krótsza pauza, równoległe strony).

### Znane ograniczenia
- `blur()` może uruchomić skrypty strony (np. zamknąć menu) – wtedy zrzut „bez fokusu” różni się nie tylko fokusem. Zdarza się rzadko, wynik i tak idzie do weryfikacji.
- Karuzele i animacje JS zmieniają obraz między zrzutami (fałszywa „zmiana”). CSS-owe animacje wyłącza Playwright (`animations="disabled"`).
- Wskaźnik fokusu rysowany dalej niż 10 px od elementu (np. podświetlenie całego wiersza) nie jest widoczny w wycinku → możliwy fałszywy `brak`.
- Nie wchodzimy do `iframe` (fokus na samym `iframe` jest odnotowany, jego wnętrze nie).
- Nie wykrywamy elementu zasłoniętego przez przyklejony nagłówek (to kryterium 2.4.11 z WCAG 2.2, poza naszym zakresem 2.1).
- Kolejność fokusu (2.4.3) oceniamy tylko pośrednio – przez `mapa-fokusu.png`.

## 2. Model wizyjny

### Do czego potrzebujemy modelu wizyjnego
1. **Opis obrazu dla oceny altu (F9, osoba 3):** moduł Tomka ma parametr `obraz_opis` – bez niego nie da się ocenić, czy alt pasuje do obrazu.
2. **Tekst na obrazach (F13):** znaleźć napisy wtopione w grafiki i ich położenie.
3. **Pomocniczo:** baner cookies, mapa fokusu (2.4.3), ogólny opis strony do raportu.

### Kandydaci
Ograniczenie sprzętowe: lokalny GPU RTX 2060 6 GB (Gemma 3 4B działa, Qwen2.5-VL nie – patrz wyniki); Colab T4 15 GB (jak Bielik u osoby 3).

| Model | Uruchomienie | Rozmiar (Q4) | Uwagi |
|---|---|---|---|
| Qwen2.5-VL 3B | Ollama `qwen2.5vl:3b` | ok. 3 GB | mieści się w 6 GB, mocny w OCR |
| Gemma 3 4B | Ollama `gemma3:4b` | ok. 3,3 GB | mieści się w 6 GB, dobra wielojęzyczność |
| Qwen2.5-VL 7B | Ollama `qwen2.5vl:7b` | ok. 6 GB | lokalnie na granicy pamięci; na Colab T4 bez problemu |
| model komercyjny przez API | API zgodne z OpenAI | – | punkt odniesienia jakości; potrzebny i tak w F16 |

### Test na 10 zrzutach
Zrzuty: 5 migawek zespołu × (pierwszy ekran po zamknięciu banera + ekran z banerem cookies). Każdy zrzut dostaje 3 zadania (prompty po polsku, odpowiedź w JSON): `opis`, `tekst` (teksty na obrazach + czytelność), `baner` (czy jest baner cookies i czy ma przycisk odrzucenia). Zadanie `baner` sprawdzamy automatycznie z `meta.json`, `opis` i `tekst` oceniamy ręcznie w kolumnie `ocena_reczna`.

```powershell
ollama pull gemma3:4b
python scripts/test_modelu_wizyjnego.py --model gemma3:4b
# tylko CPU (np. gdy model zwraca śmieci na GPU):
python scripts/test_modelu_wizyjnego.py --model qwen2.5vl:3b --cpu --timeout 600
```

### Wyniki: Qwen2.5-VL 3B (14.11.2026)
Szczegóły z oceną ręczną: [`docs/wyniki/wizja_qwen2.5vl_3b_cpu.csv`](wyniki/wizja_qwen2.5vl_3b_cpu.csv).

**Na GPU (RTX 2060) model nie działa:** przy każdym zrzucie zwraca ciąg „@@@@…”, a Ollama przerywa generowanie („token repeat limit reached”). Sam tekst bez obrazu działa, wyłączenie flash attention nie pomaga. Najpewniej to problem obliczeń fp16 na kartach serii RTX 20xx (Turing). Test przeprowadziliśmy więc na **CPU** (`--cpu`).

| Zadanie | Wynik | Komentarz |
|---|---|---|
| `opis` | **9/10** trafnych | rozpoznaje stronę i jej główną treść; 1 opis ze zmyśleniem („Biały Stok”, „deportacje”); w 2 przypadkach przepisał z promptu `typ_strony: "urząd\|uczelnia"` |
| `tekst` (tekst na obrazach) | **0/10** | zawsze pusta lista, choć w zadaniu `opis` sam cytuje napisy z grafik (np. „Black Weeks … -70%” na x-kom.pl) – nie radzi sobie z zadaniem, a nie z odczytem |
| `baner` (baner cookies) | **6/10** = tylko przypadki z banerem | zawsze odpowiada „jest baner” i przepisuje przykładowe napisy przycisków z promptu; prawdziwe napisy odczytał tylko raz (x-kom.pl) |
| poprawny JSON | 20/30 | `tekst` zwraca listę zamiast obiektu; część odpowiedzi w bloku \`\`\`json (parser to obsługuje) |

| Parametr | Wartość |
|---|---|
| Rozmiar modelu | 3,2 GB (Q4), w pamięci ok. 2,8 GB |
| Czas na CPU | ok. 65 s na pierwsze zapytanie do zrzutu (kodowanie obrazu), 3–5 s na kolejne pytania o ten sam zrzut |
| Koszt | 0 zł (lokalnie); na CPU za wolno do skanowania wielu podstron |

### Wyniki: Gemma 3 4B (14.11.2026)
Szczegóły z oceną ręczną: [`docs/wyniki/wizja_gemma3_4b.csv`](wyniki/wizja_gemma3_4b.csv). Te same prompty, te same zrzuty, **na GPU** (RTX 2060) bez problemów.

| Zadanie | Wynik | Komentarz |
|---|---|---|
| `opis` | **7/10** | rozpoznaje typ strony i treść, ale przekręca nazwy własne: „Gmina Wiszków” (2×), zmyślony „Serwis Przyszłości Polski” na gov.pl |
| `tekst` (tekst na obrazach) | **8/10** | znajduje napisy z grafik (plakat na pb.edu.pl, banery x-kom.pl i wasilkow.pl, zdjęcie na bialystok.pl); błędy OCR („Raby do -70%”, „60 UU ZU Z”) i mieszanie z tekstem HTML (menu, treść banera cookies) |
| ocena czytelności | **niespójna** | ten sam napis na bialystok.pl raz „nieczytelny – niski kontrast”, raz „czytelny” |
| `baner` (baner cookies) | **9/10** | poprawnie mówi „nie ma banera” na 4 z 5 ekranów bez banera; poprawnie wykrywa brak przycisku odrzucenia na wasilkow.pl; 1 fałszywy alarm (x-kom.pl, zmyślone przyciski) |
| poprawny JSON | **30/30** | odpowiedzi w bloku \`\`\`json – parser to obsługuje |

| Parametr | Wartość |
|---|---|
| Rozmiar modelu | 3,4 GB (Q4), w pamięci GPU ok. 4,0 GB (kontekst 4096) |
| Czas na GPU | średnio **5,4 s** na zapytanie (4,2–8,7 s); strona z 30 obrazami ≈ 3 min na jedno pytanie na obraz |
| Koszt | 0 zł (lokalnie, karta 6 GB wystarcza) |

### Porównanie i decyzja wstępna
| | Qwen2.5-VL 3B | Gemma 3 4B |
|---|---|---|
| działa na RTX 2060 | nie (tylko CPU, ~65 s) | tak (~5 s) |
| opis strony | 9/10 | 7/10 (przekręca nazwy własne) |
| tekst na obrazach | 0/10 | 8/10 |
| baner cookies | 6/10 (zawsze „tak”) | 9/10 |
| poprawny JSON | 20/30 | 30/30 |

- **Wybór na sprint 2: Gemma 3 4B lokalnie przez Ollamę** – jedyny z testowanych, który działa na naszym sprzęcie i wykonuje wszystkie 3 zadania. Do sprawdzenia w sprincie 2 na Colab T4: Qwen2.5-VL 7B, oraz model komercyjny przez API jako punkt odniesienia (skrypt obsługuje oba bez zmian).
- **Qwen2.5-VL 3B odrzucamy:** nie działa na RTX 2060, a na CPU nie wykonuje zadań wymagających precyzji (pusta lista tekstów, zawsze „jest baner”).
- **Opis obrazu (`obraz_opis` dla F9):** Gemma się nadaje, ale nazw własnych z jej opisu nie wolno traktować jako pewnych („Wiszków”). Ocena altu powinna porównywać treść obrazu, a nie nazwy.
- **Tekst na obrazach (F13): model znajduje napisy, ale kontrastu nie liczy.** Ten sam napis raz uznał za czytelny, raz nie, a odczyt bywa przekręcony. Model wskazuje kandydatów, kontrast liczy kod (sekcja 3), a do odczytu napisów porównamy jeszcze OCR z językiem polskim (np. Tesseract, PaddleOCR).
- **Model miesza tekst z obrazów ze zwykłym tekstem HTML.** W F13 trzeba podawać mu wycinki samych obrazów z DOM (`<img>`, `background-image`), a nie cały zrzut.
- **Prompty nie mogą zawierać przykładowych odpowiedzi** („Odrzuć”, „urząd|uczelnia”) – mały model je przepisuje. To ta sama lekcja co u osoby 3 (v2 promptu altu).

## 3. Kontrast tekstu na obrazach (F13) – decyzja wstępna
Modele wizyjne źle podają liczby (np. współczynnik kontrastu), za to dobrze czytają tekst i wskazują jego położenie. Dlatego dzielimy pracę:
1. **Kandydaci z DOM:** elementy `<img>`, `background-image`, `<svg>` i `<canvas>` z położeniem na zrzucie (obrazy bez napisów odpadają szybko).
2. **Model wizyjny:** dla wycinka zrzutu z obrazem zwraca napisy i ich prostokąty (`bbox`).
3. **Kod liczy kontrast:** w prostokącie napisu dzielimy piksele na 2 grupy kolorów (k-means, k=2) → kolor tekstu i tła → wzór WCAG (4,5:1 dla zwykłego tekstu, 3:1 dla dużego). Dla tła zdjęciowego bierzemy najgorszy fragment (np. 10. percentyl), nie średnią.
4. Wynik zawsze `do_weryfikacji`, kryterium 1.4.3, pewność z jakości dopasowania 2 grup kolorów.

Funkcje `kontrast()` i `luminancja()` z `audytor.fokus.pomiar` wykorzystamy także tutaj.

## Do uzgodnienia
- **Z osobą 2 (model danych, F7):** wyniki fokusu mają już pola `Problem` (`regula`, `kryteria_wcag`, `status`, `poziom_pewnosci` …). Ustalić, czy test fokusu to `zrodlo: "ai"`, czy dodajemy osobne źródło (np. `"heurystyka"`). Teraz jest `"ai"`, bo `Zrodlo` ma tylko `axe` i `ai`.
- **Z osobą 3 (AI tekst, F9):** format `obraz_opis` – proponuję krótki opis po polsku (1–2 zdania) + lista tekstów widocznych na obrazie.
- **Z osobą 6 (backend):** test fokusu trwa ok. 1 s na element – w przebiegu skanu powinien iść w workerze Celery, z limitem kroków.
