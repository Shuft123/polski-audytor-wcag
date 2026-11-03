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

**Do ustalenia z osobą 2:** axe-core działa obecnie na stronie **po** zamknięciu banera. Osobny audyt banera (stan przed zamknięciem) – do zaplanowania w kolejnych sprintach.

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

## 2. Format pojedynczego wyniku z audytu
Zgodnie z wymaganiami MVP (Model danych v1), każdy wykryty problem (zarówno z axe-core, jak i AI) musi mieć wspólny format przed zapisem do bazy.
Wstępne pola do JSONa (do przedyskutowania):
- `url_podstrony`: string
- `zrodlo`: string ("axe" lub "ai")
- `kryterium_wcag`: string
- `waga`: string/int
- `selektor`: string
- `fragment_html`: string
- `poziom_pewnosci`: float (dla AI)
- `status`: string ("blad", "do weryfikacji", itp.)
