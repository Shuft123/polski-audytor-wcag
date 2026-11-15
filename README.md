# polski-audytor-wcag

Polski audytor dostępności cyfrowej (WCAG 2.1 AA) – projekt zespołowy, Politechnika Białostocka.

## Szybki start: skanuj adres

```
pip install -e ".[dev]"
python -m playwright install chromium
audytor-scan https://www.wasilkow.pl/
```

Strona jest renderowana w Chromium, sprawdzana przez axe-core (WCAG 2.0/2.1 A i AA), a w folderze
`wyniki/<strona>/` lądują migawka (DOM, zrzut ekranu, `meta.json`) i `wynik.json` z listą problemów.
Zapis także w bazie: `audytor-scan https://www.wasilkow.pl/ --db sqlite:///audytor.db`.
Wszystkie opcje: `audytor-scan --help`.

## Moduły

- **Crawler** (`src/audytor/crawler`) – renderowanie stron, migawki, linki wewnętrzne, robots.txt. Instrukcja: [docs/crawler.md](docs/crawler.md).
- **Deklaracja dostępności** (`src/audytor/deklaracja`) – wykrywanie linku do deklaracji (F17), wymogi do walidacji (F18). Instrukcja: [docs/deklaracja.md](docs/deklaracja.md), checklista: [docs/deklaracja-checklista.md](docs/deklaracja-checklista.md).
- **Test fokusu** (`src/audytor/fokus`) – przejście stroną klawiszem Tab i ocena widoczności fokusu (WCAG 2.4.7). Instrukcja i wybór modelu wizyjnego: [docs/ai-wizja-fokus.md](docs/ai-wizja-fokus.md).

## Dokumentacja

- [Kontrakt danych między modułami](docs/kontrakt-danych.md)
- [Model danych v1 (ERD)](docs/model-danych.md)
- [Konwencje i zasady współpracy](docs/konwencje.md)
