# Moduł crawlera (`audytor.crawler`)

Osoba 1, sprint 1. Funkcjonalności: F3 (renderowanie JS, DOM, zrzuty), F2 (robots.txt, tempo zapytań), F1 w wersji okrojonej (linki wewnętrzne z jednej strony).
Format wyników: [kontrakt-danych.md, sekcja 1](kontrakt-danych.md#1-format-migawki-strony-crawler---reszta).

## Instalacja (jednorazowo)

Wymagany Python 3.11+. W głównym folderze repozytorium:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m playwright install chromium
```

Jeśli PowerShell blokuje `Activate.ps1`, można pominąć aktywację i wywoływać Pythona wprost: `.\.venv\Scripts\python.exe -m ...`.

## Uruchamianie

```powershell
# jedna strona -> tests/data/snapshots/pb-edu-pl/
python -m audytor.crawler https://pb.edu.pl/

# kilka stron, własny folder wyjściowy
python -m audytor.crawler https://pb.edu.pl/ https://www.gov.pl/ --out wyniki

# adresy z pliku (jak migawki testowe w repo)
python -m audytor.crawler --urls-file tests/data/strony-testowe.txt --jpeg --no-mhtml

# pełne migawki z kopią offline (MHTML) do pracy lokalnej – poza repozytorium
python -m audytor.crawler --urls-file tests/data/strony-testowe.txt --out migawki-lokalne
```

Po `pip install -e .` działa też krótsza komenda `audytor-crawl ...`.

| Opcja | Domyślnie | Opis |
|---|---|---|
| `--out DIR` | `tests/data/snapshots` | folder wyjściowy |
| `--name NAZWA` | z adresu | nazwa folderu migawki (tylko przy jednym adresie) |
| `--urls-file PLIK` | – | adresy z pliku, jeden w linii, `#` = komentarz |
| `--delay S` | `1` | pauza między stronami tej samej witryny; jeśli robots.txt ma `Crawl-delay`, brana jest większa wartość |
| `--timeout S` | `30` | limit wczytania strony |
| `--viewport WxH` | `1366x768` | rozmiar okna przeglądarki |
| `--max-height PX` | `15000` | maks. wysokość zrzutu; dłuższe strony są przycinane |
| `--jpeg` | PNG | zrzut w JPEG (kilka razy mniejszy) |
| `--no-mhtml` | zapisuje | bez kopii offline `page.mhtml` |
| `--no-scroll` | przewija | nie przewijaj strony (obrazki „lazy” mogą się nie wczytać) |
| `--ignore-robots` | sprawdza | pomija robots.txt – **tylko dla własnych stron testowych** |
| `--keep-cookie-banner` | zamyka | nie zamykaj banera cookies (gdy audytujemy sam baner) |
| `--headed` | ukryta | pokazuje okno przeglądarki (przydatne przy debugowaniu) |
| `--channel msedge` / `chrome` | Chromium z Playwrighta | używa Edge'a lub Chrome'a zainstalowanego w systemie (obejście, gdy pełny Chromium z Playwrighta nie startuje – patrz niżej) |

Kod wyjścia: `0` – wszystkie strony zapisane, `1` – co najmniej jedna pominięta lub z błędem, `2` – złe argumenty, `3` – nie udało się uruchomić przeglądarki.

## Jak to działa

1. Adres jest normalizowany i sprawdzany w robots.txt (RFC 9309: 4xx = brak ograniczeń, 5xx/brak połączenia = nie skanujemy). Crawler przedstawia się jako `PolskiAudytorWCAG/<wersja>` i respektuje reguły dla tej nazwy oraz `*`.
2. Chromium (Playwright) otwiera stronę, czeka na `load`, potem do 5 s na wyciszenie sieci, przewija stronę (obrazki „lazy”) i odczekuje 1 s.
3. Baner cookies: przez maks. 2 s szukany jest baner zgody (część stron pokazuje go z opóźnieniem albo dopiero po przewinięciu). Jeśli jest, zapisywany jest zrzut okna z banerem, a baner zamykany przyciskiem **odrzucenia / tylko niezbędne** – nigdy „akceptuj wszystkie”. Przycisk rozpoznawany jest po identyfikatorach popularnych systemów zgód (OneTrust, Cookiebot, Didomi, CookieYes…) albo po napisie („Odrzuć”, „Odrzucam niewymagane”, „Akceptuję wymagane”, „Tylko niezbędne”…) i tylko wewnątrz elementu, który mówi o cookies/prywatności. Szczegóły: `src/audytor/crawler/cookies.py`.
4. Zapisywane są: DOM z dopisanym `<base href>`, zrzut całej strony, opcjonalnie MHTML, oraz `meta.json` z linkami wewnętrznymi (podzielonymi na dozwolone/zablokowane przez robots.txt), linkami do dokumentów i wynikiem obsługi banera.
5. Błąd jednej strony nie przerywa pozostałych – jest wypisywany, a kod wyjścia to `1`.

## Użycie z innych modułów

```python
from audytor.crawler import Renderer, RenderOptions, save_snapshot

with Renderer(RenderOptions(screenshot_type="jpeg")) as renderer:
    # a) tylko migawka
    snapshot = renderer.render("https://pb.edu.pl/")
    save_snapshot(snapshot, "wyniki")

    # b) żywa strona, np. dla axe-core (osoba 2) albo testu fokusu (osoba 4)
    with renderer.open("https://pb.edu.pl/") as opened:
        page = opened.page                    # playwright.sync_api.Page
        ...                                   # uruchom axe / naciskaj Tab
        snapshot = renderer.capture(opened)   # migawka z tej samej sesji
```

Wyjątki: `RobotsDisallowedError` (strona zablokowana w robots.txt), `RenderError` (nie udało się otworzyć strony).

Odczyt gotowej migawki: `audytor.crawler.load_meta("tests/data/snapshots/gov-pl")`.

## Testy

```powershell
python -m pytest                    # wszystkie testy (ok. 20 s)
python -m pytest -m "not browser"   # tylko testy bez przeglądarki (np. w CI bez Chromium)
```

- `tests/crawler/test_links.py`, `test_robots.py`, `test_snapshot.py`, `test_cookies.py` – logika bez sieci i bez przeglądarki (m.in. które napisy przycisków są uznawane za „odrzuć”).
- `tests/crawler/test_render_browser.py` – cały przebieg w prawdziwym Chromium na lokalnym serwerze HTTP (bez internetu): robots.txt, CLI, banery cookies (odrzucenie, baner bez opcji odrzucenia, baner z opóźnieniem, przycisk „Odrzuć” poza banerem). Pomijany automatycznie, gdy Chromium nie jest zainstalowany.

Do CI (osoba 6): przed testami potrzebne `python -m playwright install --with-deps chromium`, inaczej testy `browser` zostaną pominięte.

## Rozwiązywanie problemów

- **`Executable doesn't exist ...`** – brak przeglądarki: `python -m playwright install chromium`.
- **`--headed` nie startuje** (np. `spawn UNKNOWN`, w dzienniku zdarzeń Windows błąd SideBySide), a bez `--headed` wszystko działa – tryb bez okna używa osobnej, lżejszej przeglądarki (`chromium_headless_shell`). Obejście: `--headed --channel msedge`.
- **Kod wyjścia `3`** – przeglądarka w ogóle się nie uruchomiła; komunikat podpowiada, co zrobić.
- **U asystenta AI (np. Claude z Desktop Commanderem) testy przechodzą, a w Twoim terminalu nie** – aplikacja ze Sklepu Microsoft ma prywatną kopię `AppData\Local`, więc przeglądarki zainstalowane z jej poziomu są niewidoczne dla zwykłego terminala. Zainstaluj je we własnym terminalu: `.\.venv\Scripts\python.exe -m playwright install chromium`.

## Znane ograniczenia (sprint 1)

- Baner cookies bez opcji odrzucenia (np. wasilkow.pl – tylko „Akceptuję”) zostaje na zrzucie; nietypowe banery mogą nie zostać rozpoznane. Zawsze jest wtedy ostrzeżenie w `warnings`.
- Linki zbierane tylko z jednej strony; pełny crawling witryny, kolejka i limity – sprint 3 (F1, F4).
- Poddomeny (np. `bip.gmina.pl`) traktowane są jako osobne witryny.
- Niektóre strony zgłaszają absurdalną wysokość (np. bialystok.pl z otwartym banerem: ponad 33 mln px) – zrzut jest wtedy przycinany do `--max-height`.
