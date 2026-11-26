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

## Skan wielu podstron przez API i worker (sprint 2)

Skan zlecony przez API sprawdza stronę startową i podane podstrony – axe-core na każdej z nich:

```
curl -X POST http://localhost:8000/skany -H "Content-Type: application/json" -d '{
  "url": "https://www.wasilkow.pl/",
  "parametry": {
    "podstrony": ["https://www.wasilkow.pl/kontakt", "https://www.wasilkow.pl/deklaracja-dostepnosci"],
    "max_podstron": 20
  }
}'
```

W PowerShellu łatwiej przez Swaggera: http://localhost:8000/docs → `POST /skany` → „Try it out”.

| Parametr | Domyślnie | Znaczenie |
|---|---|---|
| `podstrony` | `[]` | Adresy do sprawdzenia oprócz strony startowej. Inne witryny (także poddomeny, np. `bip.…`) są pomijane, duplikaty i fragmenty `#…` usuwane. |
| `max_podstron` | 20 | Ile podstron najwyżej, licząc stronę startową. Twardy limit: 50. |

Jak działa (`audytor.worker.zadania.wykonaj_skan`):
- **Jedna przeglądarka na cały skan**; podstrony po kolei, strona startowa pierwsza.
- **Limit tempa na witrynę:** między podstronami tej samej witryny pauza `AUDYTOR_OPOZNIENIE_S` (1 s)
  albo Crawl-delay z robots.txt, jeśli jest większy (`audytor.skan.Ogranicznik`). robots.txt jest sprawdzany
  dla **każdej** podstrony (robi to crawler przy otwieraniu strony).
- **Błąd jednej podstrony nie przerywa skanu.** Podstrona zablokowana w robots.txt albo niewczytana w limicie
  czasu trafia do bazy z polem `blad` (w API: `"blad": "Pominięto zgodnie z robots.txt – …"`), bez problemów.
- **Postęp widać w trakcie:** każda podstrona jest zapisywana zaraz po sprawdzeniu – `GET /skany/{id}` pokazuje
  rosnące `liczba_podstron`.
- **Status skanu:** `zakonczony`, gdy sprawdzono choć jedną podstronę; `blad`, gdy żadnej (powód w `opis_bledu`).
- **Budżet czasu:** po 480 s (zapas przed limitem zadania Celery – 540 s) kolejne podstrony nie są już
  otwierane, tylko zapisywane z `blad` „przekroczony czas skanu”. Dłuższe skany – kolejka F4 w sprincie 3.
- Dwa adresy, które przekierowują na tę samą stronę, dają jedną podstronę.

Lista podstron w sprincie 3 przyjdzie z crawlera wielu podstron (F1, osoba 1) – worker użyje jej tak samo
jak `parametry["podstrony"]` (funkcja `audytor.skan.lista_podstron`).

Z wiersza poleceń kilka podstron sprawdza też `audytor-scan` (bez bazy albo z `--db`):

```
python -m audytor.skan https://www.wasilkow.pl/ https://www.wasilkow.pl/kontakt --db sqlite:///audytor.db
```

## Znane ograniczenia

- Treść w `<iframe>` nie jest jeszcze sprawdzana (axe działa w głównej ramce).
- Testy automatyczne wykrywają tylko część problemów WCAG – resztę mają uzupełniać moduły AI i audytor.
- Wersja axe-core zależy od pakietu `axe-playwright-python` (obecnie 4.12.1); przy jego aktualizacji
  warto podmienić `locales/pl.json` (instrukcja w `src/audytor/axe/locales/README.md`).
