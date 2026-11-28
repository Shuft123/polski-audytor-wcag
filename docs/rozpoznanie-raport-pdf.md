# Rozpoznanie: biblioteka do raportu PDF (F22)

Osoba 6, sprint 2. Raport PDF z audytu powstaje w sprincie 4 – tu wybór biblioteki i prototyp.

## Wniosek

**WeasyPrint** (HTML + CSS → PDF) w trybie **PDF/UA-1**.

Najważniejsze kryterium: raport z audytora dostępności **sam musi być dostępnym PDF-em**. Musi mieć
strukturę (tagi) czytelną dla czytnika ekranu, język dokumentu i alternatywne opisy zrzutów. Raport
niedostępny podważałby wiarygodność całego narzędzia, a urzędy, dla których jest przeznaczony,
same podlegają wymogom dostępności.

## Prototyp

`scripts/prototyp_raport_pdf.py` generuje ten sam fragment raportu obiema bibliotekami: nagłówki,
akapit z polskimi znakami, tabelę problemów z podpisem i nagłówkami kolumn oraz zrzut z altem. Potem
bada strukturę obu PDF-ów przez pikepdf (tej biblioteki używa też rozpoznanie audytu PDF, `docs/rozpoznanie-pdf.md`).

| | WeasyPrint 70 (`pdf_variant="pdf/ua-1"`) | ReportLab 5.1 (open source) |
|---|---|---|
| Drzewo struktury (`/StructTreeRoot`, tagged PDF) | ✅ | ❌ brak |
| Tagi | `H1`, `H2`, `P`, `Table`, `THead`, `TH`, `TD`, `Caption`, `Figure`… | – |
| Alt obrazu (`/Figure /Alt`) | ✅ z atrybutu `alt` w HTML | ❌ |
| Język dokumentu (`/Lang`) | ✅ z `<html lang="pl">` | ✅ (parametr `lang`) |
| Oznaczenie PDF/UA w metadanych | ✅ `pdfuaid:part=1` | ❌ |
| Polskie znaki, osadzone fonty | ✅ | ✅ |
| Jak się pisze raport | szablon HTML + CSS (`@page`, numeracja stron) | kod Pythona (Platypus), układ ręcznie |
| Czas (raport 1 strona) | ok. 0,6 s | < 0,01 s |

ReportLab sam przyznaje, że przy jego niskopoziomowym podejściu dostępność zależy od programisty.
W wersji open source nie da się zbudować drzewa tagów. Szybkość nie ma tu znaczenia: raport powstaje raz na skan.

## Zalety WeasyPrint dla projektu

- **Ten sam HTML co dashboard (sprint 7).** Szablon raportu (np. Jinja2) może współdzielić style
  z dashboardem, a zespół pisze HTML zamiast kodu układu strony.
- **Dostępność wynika z semantyki HTML.** Poprawne `<h1>`, `<table>` z `<th scope>`, `<caption>`
  i `alt` dają poprawne tagi PDF. Szablon można więc sprawdzić naszym własnym audytorem (axe-core),
  zanim powstanie PDF.
- **Zgodność z PDF/UA da się sprawdzić automatycznie** walidatorem veraPDF (z rozpoznania audytu PDF)
  w CI. Uwaga: dokumentacja pandoc nazywa tryb PDF/UA w WeasyPrint eksperymentalnym, więc **walidacja
  w CI jest konieczna**, a nie opcjonalna.

## Koszty i ryzyka

- **Biblioteki systemowe.** WeasyPrint wymaga Pango. W `Dockerfile` trzeba dodać `libpango-1.0-0`
  i `libpangoft2-1.0-0` (do sprawdzenia przy wdrożeniu; część zależności instaluje już
  `playwright install --with-deps`). Na Windowsie lokalnie: instalator GTK albo praca w Dockerze.
- **Bezpieczeństwo.** WeasyPrint nie powinien renderować niezaufanego HTML. Do szablonu trafiają
  dane z audytowanych stron (fragmenty HTML, alty), więc szablon musi je **escapować** (Jinja2
  `autoescape=True`), a pobieranie zasobów z sieci powinno być wyłączone (własny `url_fetcher`).
- **Duże raporty.** 50 podstron ze zrzutami to dziesiątki MB. Zrzuty trzeba zmniejszać, np. do
  szerokości strony A4, i trzymać jako JPEG (Pillow jest już w zależnościach).

## Propozycja na sprint 4 (raport)

1. Szablon `src/audytor/raport/szablon.html` (Jinja2 + CSS) z danymi z `GET /skany/{id}/wyniki`.
2. `audytor.raport.generuj(skan_id) -> Path` + endpoint `GET /skany/{id}/raport.pdf`.
3. CI: wygenerowanie raportu przykładowego skanu i walidacja veraPDF (profil PDF/UA-1).
4. Test szablonu HTML axe-core'em (własne narzędzie).

## Źródła

- WeasyPrint – obsługa PDF/A i PDF/UA (od wersji 57, eksperymentalna): https://pandoc.org/demo/example33/19.3-weasyprint.html
- WeasyPrint – zgłoszenie o PDF/A-a, potwierdzające obsługę PDF/UA-1: https://github.com/Kozea/WeasyPrint/issues/2574
- ReportLab – dostępność PDF (RML, przykład 55): https://www.reportlab.com/examples/rml/test/test_055_accessibility.pdf
- PDF Association – Tagged PDF Best Practice Guide (PDF/UA): https://pdfa.org/wp-content/uploads/2023/07/Tagged-PDF-Best-Practice-Guide.pdf
