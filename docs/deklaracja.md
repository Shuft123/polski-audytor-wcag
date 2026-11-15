# Moduł deklaracji dostępności (`audytor.deklaracja`)

Osoba odpowiedzialna: Maciej Klepacki (osoba 5) · zastępstwo: Łukasz Perkowski (osoba 6)
Funkcjonalności: **F17** wykrycie deklaracji (gotowe w wersji 1), **F18** walidacja (sprint 3–4), **F19** zgodność z wynikami (sprint 8).
Wymogi prawne: [deklaracja-checklista.md](deklaracja-checklista.md).

## Jak działa wykrywanie (F17)

1. **Kandydaci z DOM strony głównej** (bez sieci, `find_in_html`). Każdy link `<a href>` dostaje punkty:

   | Sygnał | Punkty |
   |---|---|
   | meta tag `deklaracja-dostępności` | +100 |
   | tekst / `aria-label` / `title` / `alt` obrazka: „deklaracja dostępności” (też „accessibility statement”) | +60 |
   | tekst: „deklaracja” + „dostępność” | +50 |
   | tekst: „dostępność cyfrowa” | +25 |
   | tekst: „dostępność” (rzeczownik – **nie** „dostępny/dostępna”) | +20 |
   | adres zawiera `deklaracja-dostepnosci` | +30 |
   | adres zawiera `deklaracja` (tylko gdy pasuje też tekst – inaczej łapiemy deklaracje podatkowe) | +15 |
   | adres zawiera `dostepnosc` / `accessibility` | +10 |
   | link w stopce (`<footer>`, `role="contentinfo"`, id/klasa z „footer”/„stopka”) | +15 |
   | inna strona o dostępności (architektoniczna, PJM, ETR, koordynator…) bez słowa „deklaracja” | −15 |
   | link na inną domenę (np. BIP) | −5 |

   Kandydat musi mieć co najmniej 20 punktów. Pewność = punkty / 100 (maks. 1,0).

2. **Weryfikacja** (z siecią, `find_declaration`). Pobieramy 3 najlepszych kandydatów i liczymy identyfikatory `a11y-*`. Wygrywa zweryfikowana strona z największą liczbą identyfikatorów. Gdy żaden kandydat nie jest deklaracją, sprawdzamy typowe adresy (`/deklaracja-dostepnosci` itd.) – wtedy `method = "typowy_adres"` i ostrzeżenie, że brakuje linku na stronie głównej.

   Zawsze sprawdzamy `robots.txt` (wspólny `RobotsCache` z crawlera) i robimy pauzę między zapytaniami (domyślnie 1 s). Gdy `robots.txt` jest nieosiągalny (np. błąd SSL, brak domeny), zgodnie z RFC 9309 nie pobieramy strony – komunikat podaje prawdziwą przyczynę.

3. **Przeglądarka zapasowa** (gdy zainstalowany Playwright; wyłączenie: `--bez-przegladarki`). Stronę pobieramy przez Chromium z modułu crawlera, gdy:
   - Python zgłasza błąd certyfikatu SSL (np. bialystok.pl – niepełny łańcuch certyfikatów),
   - serwer odrzuca zwykłe zapytanie kodem 401/403/429/503 (ochrona przed botami w sklepach),
   - strona główna ma mniej niż 5 linków (budowana w JS).

   Każde takie użycie jest zapisane w `warnings`.

4. **Certyfikaty systemowe.** CLI włącza pakiet `truststore` (zależność projektu), który sprawdza certyfikaty przez magazyn systemu. Windows i macOS same uzupełniają niepełne łańcuchy, więc błąd `CERTIFICATE_VERIFY_FAILED` zwykle znika bez przeglądarki. **Dotyczy też crawlera** – warto dodać `truststore.inject_into_ssl()` w jego CLI.

## Stan wyniku (`status`)

| Stan | Znaczenie | Na ekranie |
|---|---|---|
| `zweryfikowana` | strona ma identyfikatory `a11y-*` albo tytuł i formułę deklaracji | `OK` |
| `bez_a11y` | silny link („Deklaracja dostępności”), strona działa, ale bez `a11y-*` – u sklepu zwykle informacja PAD, u urzędu deklaracja niezgodna z warunkami technicznymi | `BEZ_A11Y` |
| `niezweryfikowana` | tryb bez sieci (`--snapshot`) – znaleziono tylko link | `OK` |
| `brak` | nie znaleziono; przyczyna w `warnings` (wypisywana jako „powód:”) | `BRAK` |

## Uruchamianie

```bash
# bez sieci – na migawkach crawlera
python -m audytor.deklaracja --snapshot tests/data/snapshots/*

# z siecią, cała lista testowa, podsumowanie do CSV
python -m audytor.deklaracja --urls-file tests/data/strony-testowe-deklaracja.csv --csv wyniki-deklaracji.csv --out wyniki-deklaracji.json

# strona główna zawsze renderowana w przeglądarce (domyślnie tylko gdy trzeba)
python -m audytor.deklaracja https://www.mediaexpert.pl --render
```

## Użycie z kodu (dla osoby 6 – integracja ze skanem)

```python
from audytor.crawler import Renderer
from audytor.deklaracja import find_declaration

with Renderer() as renderer, renderer.open("https://www.wasilkow.pl/") as opened:
    wynik = find_declaration(opened.final_url, html=opened.page.content())

wynik.found, wynik.declaration_url, wynik.confidence   # True, "https://…", 0.95
wynik.to_dict()                                         # gotowe do JSON / bazy
```

## Format wyniku (przykład z wymyśloną gminą)

```json
{
  "site_url": "https://gmina.example.pl/",
  "found": true,
  "declaration_url": "https://gmina.example.pl/deklaracja-dostepnosci",
  "status": "zweryfikowana",
  "method": "link",
  "confidence": 0.95,
  "verified": true,
  "a11y_ids": ["a11y-data-aktualizacja", "a11y-wstep", "..."],
  "missing_required_ids": ["a11y-komunikacja"],
  "candidates": [{"url": "...", "score": 105, "reasons": ["tekst: „deklaracja dostępności”", "w stopce"], "...": "..."}],
  "warnings": []
}
```

`method`: `meta` | `link` | `typowy_adres` | `brak`. Bez weryfikacji (`--snapshot` bez `--sprawdz`) `verified` jest zawsze `false`.

**Do ustalenia z osobą 2 (model danych):** brak deklaracji albo brak obowiązkowych `a11y-*` to wynik audytu (źródło `deklaracja`, kryterium: art. 10 ustawy, nie WCAG). Proponuję dodać `"deklaracja"` jako trzecią wartość pola `zrodlo` obok `axe` i `ai`.

## Znane ograniczenia (wersja 1)

- Bez przeglądarki strona główna jest pobierana bez JS. Jeśli HTML ma ≥ 5 linków, ale stopka powstaje w JS (np. um.warszawa.pl), link nie zostanie zauważony – deklaracja znajdzie się wtedy tylko pod typowym adresem. Pewny wynik daje `--render`.
- Ochrona przed botami w części sklepów może blokować także przeglądarkę headless.
- Weryfikacja liczy identyfikatory `a11y-*`, ale nie sprawdza jeszcze ich treści – to F18.
- Deklaracje w PDF są traktowane jak każdy inny kandydat (brak identyfikatorów ⇒ niezweryfikowane). F18 ma je zgłaszać jako niezgodne z warunkami technicznymi.
