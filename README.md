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
- **Audyt axe-core** (`src/audytor/axe`) – uruchomienie axe-core na stronie i zamiana wyników na wspólny format. Instrukcja: [docs/audyt-axe.md](docs/audyt-axe.md).
- **Format wyników** (`src/audytor/wyniki`) – wspólny format problemu dla axe i AI, plik `wynik.json`.
- **Baza danych** (`src/audytor/db`) – model danych v1 (skan, podstrona, problem). Opis: [docs/model-danych.md](docs/model-danych.md).
- **Skan** (`src/audytor/skan`) – komenda `audytor-scan`: render → axe-core → zapis wyniku.

## Dokumentacja

- [Kontrakt danych między modułami](docs/kontrakt-danych.md)
- [Model danych v1 (ERD)](docs/model-danych.md)
- [Konwencje i zasady współpracy](docs/konwencje.md)
