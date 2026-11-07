# Kontrakt danych między modułami

Dokument zawiera ustalony format wymiany danych, dzięki czemu moduł crawlera, modele AI, backend i raporty mogą ze sobą bezkolizyjnie rozmawiać. [Termin: do 02.11.2026]

## 1. Format migawki strony (Crawler -> Reszta)
Migawka to zapis jednej wyrenderowanej strony (po wykonaniu JavaScriptu). Tworzy ją moduł `audytor.crawler` (osoba 1). Szczegóły użycia: [crawler.md](crawler.md).

### 1.1. Gdzie
Migawki testowe leżą w `tests/data/snapshots/<nazwa>/`, jeden folder na stronę. Nazwa folderu powstaje z adresu, np. `https://www.gov.pl/web/zdrowie` -> `gov-pl_web-zdrowie`. Lista stron testowych: `tests/data/strony-testowe.txt`.

| Folder | Strona | Typ |
|---|---|---|
| `pb-edu-pl` | https://pb.edu.pl/ | uczelnia |
| `bialystok-pl` | https://www.bialystok.pl/ | duże miasto |
| `gov-pl` | https://www.gov.pl/ | administracja centralna, dużo JS |
| `x-kom-pl` | https://www.x-kom.pl/ | sklep, ciężki JS |
| `wasilkow-pl` | https://www.wasilkow.pl/ | mała gmina |

### 1.2. Co zawiera folder migawki
| Plik | Zawartość |
|---|---|
| `dom.html` | DOM po wyrenderowaniu (UTF-8). Na początku `<head>` dopisany jest `<base href="...">` z adresem strony, więc po otwarciu z dysku CSS i obrazki ładują się z oryginalnej witryny (wymaga internetu). |
| `screenshot.png` / `screenshot.jpg` | Zrzut całej strony w oknie 1366x768, **po zamknięciu banera cookies**. Strony wyższe niż 15 000 px są przycinane (informacja w `warnings`). W repozytorium trzymamy JPEG, żeby nie powiększać repo. |
| `screenshot-baner.png` / `.jpg` | (gdy wykryto baner cookies) Widok okna z banerem, **przed** jego zamknięciem – do audytu samego banera. |
| `page.mhtml` | (opcjonalnie) Samowystarczalna kopia strony ze stylami i obrazkami – działa offline. Duża (do kilkunastu MB), dlatego **nie ma jej w repozytorium**; generuje się ją lokalnie (patrz crawler.md). |
| `meta.json` | Metadane – opis poniżej. Nazwy plików w folderze zawsze czytamy z pola `files`. |

### 1.3. `meta.json`
Przykład (`tests/data/snapshots/gov-pl/meta.json`, lista linków skrócona):
```json
{
  "schema_version": "1.0",
  "requested_url": "https://www.gov.pl/",
  "final_url": "https://www.gov.pl/",
  "http_status": 200,
  "fetched_at": "2026-11-03T12:14:46+00:00",
  "title": "Portal Gov.pl",
  "lang": "pl-PL",
  "viewport": {"width": 1366, "height": 768},
  "user_agent": "Mozilla/5.0 (...) Chrome/156.0.8078.4 Safari/537.36 PolskiAudytorWCAG/0.1.0 (+https://github.com/Shuft123/polski-audytor-wcag)",
  "render_ms": 7900,
  "robots": {"robots_url": "https://www.gov.pl/robots.txt", "status": "ok", "crawl_delay": null, "error": null},
  "links": {
    "internal": [
      "https://www.gov.pl/web/premier/sklad-rady-ministrow",
      "https://www.gov.pl/web/premier",
      "..."
    ],
    "blocked_by_robots": [],
    "documents": [],
    "external_count": 3
  },
  "cookie_banner": {"checked": true, "detected": true, "dismissed": true, "method": "text", "button_text": "odrzuć", "frame_url": null},
  "files": {"dom": "dom.html", "screenshot": "screenshot.jpg", "cookie_banner_screenshot": "screenshot-baner.jpg"},
  "warnings": [
    "Sieć nie ucichła (networkidle) – możliwe doładowywane elementy"
  ]
}
```

| Pole | Znaczenie |
|---|---|
| `schema_version` | Wersja formatu. Zmiana niekompatybilna = podbicie wersji i informacja dla zespołu. |
| `requested_url` / `final_url` | Adres podany i adres końcowy po przekierowaniach. **Do wyników audytu używamy `final_url`.** |
| `http_status` | Kod HTTP głównego dokumentu; `null`, gdy strona nie wczytała się w limicie czasu. |
| `fetched_at` | Czas pobrania, ISO 8601 w UTC. |
| `title`, `lang` | `<title>` i atrybut `lang` z `<html>` (pusty napis, gdy brak – to też błąd WCAG 3.1.1). |
| `robots.status` | `ok` (reguły odczytane), `missing` (4xx – brak ograniczeń), `unreachable` (5xx/brak połączenia – strony nie skanujemy), `ignored` (sprawdzanie wyłączone). |
| `links.internal` | Podstrony tej samej witryny dozwolone przez robots.txt, bez duplikatów i fragmentów `#`. `www.` jest ignorowane, poddomeny (np. `bip.gmina.pl`) są zewnętrzne. |
| `links.blocked_by_robots` | Podstrony wewnętrzne zablokowane w robots.txt. |
| `links.documents` | Linki do PDF/DOC/DOCX/ODT/XLS itd. (do audytu dokumentów, F25/F26). |
| `links.external_count` | Liczba różnych linków zewnętrznych. |
| `cookie_banner` | Obsługa banera zgody: `checked` (czy sprawdzano), `detected`, `dismissed`, `method` (`selector` – znany system zgód, `text` – po napisie przycisku), `button_text`, `frame_url` (gdy baner był w iframe). Opis niżej. |
| `files` | Nazwy plików w folderze migawki. |
| `warnings` | Uwagi z renderowania (timeout, przycięty zrzut, kod HTTP >= 400 itd.). |

### 1.4. Baner cookies
Crawler zamyka baner zgody przyciskiem **odrzucenia** albo „tylko niezbędne” – nigdy „akceptuj wszystkie”. Dzięki temu zrzut, DOM i dalsze analizy (alt, linki, kontrast, fokus) dotyczą treści strony, a nie zasłaniającego ją banera. Przed zamknięciem zapisywany jest `screenshot-baner.*`, a wynik trafia do `cookie_banner` w `meta.json` – sam baner też podlega audytowi dostępności.

Gdy baner nie ma opcji odrzucenia (np. tylko „Akceptuję”), zostaje na stronie: `detected: true`, `dismissed: false` i ostrzeżenie w `warnings`.

Stan na migawkach testowych: zamknięty na pb.edu.pl, bialystok.pl, gov.pl i x-kom.pl; na wasilkow.pl jest tylko przycisk „Akceptuję”, więc baner zostaje.

**Ustalenie z osobą 2:** axe-core działa na stronie **po** zamknięciu banera (tak działa `audytor-scan`). Jeśli baner nie dał się zamknąć, axe sprawdza go razem ze stroną. Osobny audyt samego banera (stan przed zamknięciem) – propozycja: sprint 3–4, razem z F8 (test fokusu, bo baner musi być obsługiwalny klawiaturą). Na razie można go sprawdzić ręcznie: `audytor-scan URL --keep-cookie-banner`.

### 1.5. Praca na żywej stronie (dla axe-core i testu fokusu)
Migawki służą do pracy równoległej. W docelowym przebiegu „skanuj adres” axe-core i test fokusu działają na **tej samej otwartej stronie**, którą wyrenderował crawler:
```python
from audytor.crawler import Renderer

with Renderer() as renderer:
    with renderer.open("https://www.gov.pl/") as opened:
        wynik_axe = uruchom_axe(opened.page)      # opened.page to playwright.sync_api.Page
        migawka = renderer.capture(opened)        # DOM, zrzut, linki z tej samej sesji
```

### 1.6. Znane ograniczenia (sprint 1)
- Baner cookies jest rozpoznawany po typowych napisach przycisków i popularnych systemach zgód – na nietypowych stronach może zostać na zrzucie (zawsze z ostrzeżeniem w `warnings`).
- Zbieramy linki tylko z jednej strony (1 poziom). Pełny crawling witryny: sprint 3 (F1).


## 2. Format wyniku audytu (axe-core i AI)
Każdy wykryty problem – niezależnie od tego, czy znalazł go axe-core, czy model AI – ma ten sam format (`Problem`). Problemy jednej podstrony trafiają do pliku `wynik.json` (`WynikStrony`) obok plików migawki. Kod: `src/audytor/wyniki/format.py`, zapis w bazie: [model-danych.md](model-danych.md).

```python
from audytor.wyniki import Problem, WynikStrony, zapisz_wynik, wczytaj_wynik
```

### 2.1. Pojedynczy problem (`Problem`)
| Pole | Typ | Znaczenie |
|---|---|---|
| `id` | string | Stały identyfikator (16 znaków hex) liczony z `url_podstrony`, `zrodlo`, `regula`, `selektor`. Ten sam problem w kolejnym skanie ma ten sam `id`. Liczy się sam – nie trzeba go podawać. |
| `url_podstrony` | string | `final_url` z migawki. |
| `zrodlo` | `"axe"` \| `"ai"` | Kto wykrył problem. |
| `regula` | string | Id reguły axe (np. `image-alt`, `color-contrast`) albo testu AI. Proponowane nazwy testów AI: `ai-alt-tekst` (F9), `ai-cel-linku` (F10), `ai-naglowki` (F11), `ai-komunikaty-bledow` (F12), `ai-kontrast-obraz` (F13), `ai-fokus` (F8). |
| `kryteria_wcag` | lista stringów | Np. `["1.1.1"]`. **Lista**, bo jedna reguła może dotyczyć kilku kryteriów (np. `link-name` → `2.4.4` i `4.1.2`). Format `zasada.wytyczna.kryterium`. |
| `poziom_wcag` | `"A"` \| `"AA"` \| `"AAA"` \| null | Poziom kryterium; null dla reguł spoza WCAG. |
| `status` | `"blad"` \| `"do_weryfikacji"` \| `"odrzucony"` | `blad` – pewny błąd; `do_weryfikacji` – wymaga oceny człowieka; `odrzucony` – audytor uznał za fałszywy alarm. |
| `waga` | `"krytyczna"` \| `"powazna"` \| `"umiarkowana"` \| `"drobna"` \| null | Wpływ na użytkownika (odpowiedniki `impact` z axe: critical, serious, moderate, minor). |
| `selektor` | string | Selektor CSS elementu; `""` = cała strona. Element w iframe/shadow DOM: części rozdzielone ` >>> `. |
| `fragment_html` | string | Kod elementu, obcinany do 2000 znaków. |
| `opis` | string | Krótki opis problemu (po polsku). |
| `szczegoly` | string | Co dokładnie jest nie tak i jak poprawić. |
| `link_pomocy` | string \| null | Dokumentacja reguły. |
| `poziom_pewnosci` | float 0–1 \| null | AI: pewność modelu. axe: `1.0` dla błędów, `null` dla `do_weryfikacji`. |
| `uzasadnienie` | string \| null | Uzasadnienie oceny modelu AI. |
| `wykryto` | string | Czas wykrycia, ISO 8601 UTC. |

### 2.2. Plik `wynik.json` (`WynikStrony`)
```json
{
  "schema_version": "1.0",
  "url": "https://gmina-testowa.pl/",
  "requested_url": "https://gmina-testowa.pl",
  "http_status": 200,
  "sprawdzono": "2026-11-07T12:03:29+00:00",
  "narzedzia": {"audytor": "0.1.0", "axe-core": "4.12.1"},
  "migawka": "gmina-testowa-pl",
  "podsumowanie": {
    "liczba_problemow": 2,
    "wg_statusu": {"blad": 1, "do_weryfikacji": 1, "odrzucony": 0},
    "wg_wagi": {"krytyczna": 1, "powazna": 1, "umiarkowana": 0, "drobna": 0},
    "wg_zrodla": {"axe": 1, "ai": 1}
  },
  "ostrzezenia": [],
  "problemy": [
    {
      "id": "0b112c937ee80ff3",
      "url_podstrony": "https://gmina-testowa.pl/",
      "zrodlo": "axe",
      "regula": "image-alt",
      "kryteria_wcag": ["1.1.1"],
      "poziom_wcag": "A",
      "status": "blad",
      "waga": "krytyczna",
      "selektor": "img[src=\"a.png\"]",
      "fragment_html": "<img src=\"a.png\">",
      "opis": "Obrazy muszą mieć tekst alternatywny.",
      "szczegoly": "Napraw następujące elementy:\n  Element nie ma atrybutu alt. ...",
      "link_pomocy": "https://dequeuniversity.com/rules/axe/4.12/image-alt?application=axeAPI",
      "poziom_pewnosci": 1.0,
      "uzasadnienie": null,
      "wykryto": "2026-11-07T12:03:29+00:00"
    },
    {
      "id": "5b85f116bd688c95",
      "url_podstrony": "https://gmina-testowa.pl/",
      "zrodlo": "ai",
      "regula": "ai-alt-tekst",
      "kryteria_wcag": ["1.1.1"],
      "poziom_wcag": "A",
      "status": "do_weryfikacji",
      "waga": "powazna",
      "selektor": "img[src=\"herb.png\"]",
      "fragment_html": "<img src=\"herb.png\" alt=\"zdjęcie\">",
      "opis": "Tekst alternatywny nie opisuje obrazu.",
      "szczegoly": "Proponowany alt: „Herb gminy: złoty jeleń na czerwonym tle”.",
      "link_pomocy": null,
      "poziom_pewnosci": 0.82,
      "uzasadnienie": "Alt „zdjęcie” jest ogólnikowy; obraz przedstawia herb.",
      "wykryto": "2026-11-07T12:04:10+00:00"
    }
  ]
}
```
Pole `podsumowanie` jest wyliczane przy zapisie – przy odczycie się go nie podaje. Drugi problem to przykład, jak wynik modułu AI (osoba 3) wpisuje się w ten sam format.

### 2.3. Mapowanie wyników axe-core
Kod: `src/audytor/axe/mapowanie.py` (`axe_na_problemy`).

| axe-core | Wspólny format |
|---|---|
| jeden element (`node`) w regule | jeden `Problem` |
| `violations` | `status: "blad"`, `poziom_pewnosci: 1.0` |
| `incomplete` (axe nie umie rozstrzygnąć, np. tekst na obrazku tła) | `status: "do_weryfikacji"`, `poziom_pewnosci: null` |
| tag `wcag111`, `wcag1410` | `kryteria_wcag: ["1.1.1"]`, `["1.4.10"]` |
| tag `wcag2a` / `wcag21aa` | `poziom_wcag: "A"` / `"AA"` |
| `impact` critical / serious / moderate / minor | `waga` krytyczna / powazna / umiarkowana / drobna |
| `help`, `failureSummary`, `helpUrl` | `opis`, `szczegoly`, `link_pomocy` (komunikaty po polsku – tłumaczenie axe-core `pl`) |
| `target` | `selektor` |

Zakres reguł: tagi `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` (WCAG 2.0/2.1, poziomy A i AA). Wyniki `passes` i `inapplicable` nie są zapisywane.

### 2.4. Zasady dla modułów AI
- `zrodlo: "ai"`, `status: "do_weryfikacji"` – wyniki AI nigdy nie są twardymi błędami (definicja projektu).
- `poziom_pewnosci` obowiązkowy (0–1), `uzasadnienie` – krótko, po polsku.
- Gdy model uzna, że element jest w porządku, **nie** tworzymy problemu.
- `selektor` – ten sam co w wyniku axe dla tego elementu, jeśli to możliwe; ułatwi łączenie wyników w raporcie.

### 2.5. Wersjonowanie
`schema_version` jak w migawkach: zmiana niekompatybilna = podbicie pierwszej cyfry i informacja dla zespołu. `wczytaj_wynik` odrzuca pliki z inną główną wersją.
