# Audyt automatyczny axe-core (F6, F7)

Moduł `audytor.axe` uruchamia [axe-core](https://github.com/dequelabs/axe-core) na stronie wyrenderowanej
przez crawler i zamienia jego wyniki na wspólny format z [kontraktu danych](kontrakt-danych.md) (sekcja 2).

## Z wiersza poleceń

```
audytor-scan https://pb.edu.pl/                         # jedna strona -> wyniki/pb-edu-pl/
audytor-scan https://pb.edu.pl/ https://www.gov.pl/      # kilka stron (z pauzą i Crawl-delay)
audytor-scan --urls-file tests/data/strony-testowe.txt   # lista stron z pliku
audytor-scan https://pb.edu.pl/ --db sqlite:///audytor.db
```

Najważniejsze opcje: `--out` (folder wyników, domyślnie `wyniki`), `--db` (zapis w bazie),
`--keep-cookie-banner` (sprawdź stronę razem z banerem cookies), `--png`, `--mhtml`, `--channel msedge`.
Kod wyjścia: `0` – wszystkie strony sprawdzone, `1` – część się nie udała, `2` – błąd bazy, `3` – brak przeglądarki.

Przykładowy wynik na ekranie (strona testowa z `tests/axe/data`):
```
[1/1] https://gmina-testowa.pl/
    OK  HTTP 200  błędy: 5, do weryfikacji: 1  (krytyczna: 2, powazna: 4)
    zapisano: wyniki/gmina-testowa-pl
```

## Z kodu

```python
from audytor.crawler import Renderer
from audytor.axe import uruchom_axe, axe_na_problemy

with Renderer() as renderer:
    with renderer.open("https://www.gov.pl/") as opened:
        wynik_axe = uruchom_axe(opened.page)               # surowy wynik axe.run()
        problemy = axe_na_problemy(wynik_axe, opened.final_url)
```

Albo cały przebieg na raz (render, axe, migawka, `wynik.json`):

```python
from audytor.skan import skanuj_strone

with Renderer() as renderer:
    wynik, folder = skanuj_strone(renderer, "https://www.gov.pl/", "wyniki")
```

`axe_na_problemy` nie potrzebuje przeglądarki – działa też na wyniku axe wczytanym z pliku JSON.

## Co jest sprawdzane

- Reguły axe-core z tagami `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` (stała `DOMYSLNE_TAGI`).
- Zapisujemy `violations` (status `blad`) i `incomplete` (status `do_weryfikacji`).
- Komunikaty są po polsku (oficjalne tłumaczenie axe-core, `src/audytor/axe/locales/pl.json`);
  `uruchom_axe(page, jezyk=None)` daje oryginalne angielskie.
- axe-core działa na stronie **po** zamknięciu banera cookies (patrz kontrakt, sekcja 1.4).

## Znane ograniczenia (sprint 1)

- Treść w `<iframe>` nie jest jeszcze sprawdzana (axe działa w głównej ramce).
- Testy automatyczne wykrywają tylko część problemów WCAG – resztę mają uzupełniać moduły AI i audytor.
- Wersja axe-core zależy od pakietu `axe-playwright-python` (obecnie 4.12.1); przy jego aktualizacji
  warto podmienić `locales/pl.json` (instrukcja w `src/audytor/axe/locales/README.md`).
