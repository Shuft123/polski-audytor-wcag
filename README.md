# polski-audytor-wcag

Polski audytor dostępności cyfrowej (WCAG 2.1 AA) – projekt zespołowy, Politechnika Białostocka.

## Moduły

- **Crawler** (`src/audytor/crawler`) – renderowanie stron, migawki, linki wewnętrzne, robots.txt. Instrukcja: [docs/crawler.md](docs/crawler.md).
- **Test fokusu** (`src/audytor/fokus`) – przejście stroną klawiszem Tab i ocena widoczności fokusu (WCAG 2.4.7). Instrukcja i wybór modelu wizyjnego: [docs/ai-wizja-fokus.md](docs/ai-wizja-fokus.md).

## Dokumentacja

- [Kontrakt danych między modułami](docs/kontrakt-danych.md)
- [Konwencje i zasady współpracy](docs/konwencje.md)
