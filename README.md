# polski-audytor-wcag

[![CI](https://github.com/Shuft123/polski-audytor-wcag/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Shuft123/polski-audytor-wcag/actions/workflows/ci.yml)

Polski audytor dostępności cyfrowej (WCAG 2.1 AA) – projekt zespołowy, Politechnika Białostocka.

## Uruchomienie jedną komendą (Docker)

Wymagany [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows / macOS) albo Docker z wtyczką compose (Linux).

```
docker compose up --build
```

Startują: PostgreSQL, Redis, migracje bazy, REST API i worker Celery (z Chromium). Pierwsza budowa trwa kilka minut.
Gdy w logach pojawi się `Uvicorn running`, otwórz **http://localhost:8000/docs** – interaktywna dokumentacja API.

Skan strony przez API (z drugiego terminala albo przyciskiem „Try it out” w `/docs`):

```
curl -X POST http://localhost:8000/skany -H "Content-Type: application/json" -d "{\"url\": \"https://www.wasilkow.pl/\"}"
curl http://localhost:8000/skany/1            # status: oczekuje -> w_trakcie -> zakonczony / blad
curl http://localhost:8000/skany/1/wyniki     # problemy w formacie wynik.json
```

Zatrzymanie: `Ctrl+C`, potem `docker compose down` (`down -v` usuwa też bazę i wyniki).
Zajęty port (np. masz lokalnego PostgreSQL)? Skopiuj `.env.example` do `.env` i zmień `POSTGRES_PORT` / `API_PORT`.
Szczegóły (architektura, endpointy, zmienne środowiskowe, migracje): [docs/backend.md](docs/backend.md).

## Szybki start bez Dockera: skanuj adres

```
python -m venv .venv
.venv\Scripts\activate              # Linux / macOS: source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
audytor-scan https://www.wasilkow.pl/
```

Strona jest renderowana w Chromium, sprawdzana przez axe-core (WCAG 2.0/2.1 A i AA), a w folderze
`wyniki/<strona>/` lądują migawka (DOM, zrzut ekranu, `meta.json`) i `wynik.json` z listą problemów.
Zapis także w bazie: `audytor-scan https://www.wasilkow.pl/ --db sqlite:///audytor.db`.
Wszystkie opcje: `audytor-scan --help`.

## Testy i lint

```
pytest                 # testy z markerem "browser" pomijają się same, gdy brak Chromium
ruff check .           # linter (konfiguracja w pyproject.toml)
```

To samo uruchamia CI przy każdym pull requeście do `main` (plus migracje na PostgreSQL i skan przez docker-compose).
Pull request można zmergować dopiero, gdy CI przejdzie i ktoś z zespołu zatwierdzi zmiany – zasady: [docs/konwencje.md](docs/konwencje.md).

## Moduły

- **Crawler** (`src/audytor/crawler`) – renderowanie stron, migawki, linki wewnętrzne, robots.txt. Instrukcja: [docs/crawler.md](docs/crawler.md).
- **Audyt axe-core** (`src/audytor/axe`) – uruchomienie axe-core na stronie i zamiana wyników na wspólny format. Instrukcja: [docs/audyt-axe.md](docs/audyt-axe.md).
- **Format wyników** (`src/audytor/wyniki`) – wspólny format problemu dla axe, AI i heurystyk, plik `wynik.json`.
- **Baza danych** (`src/audytor/db`, `migrations/`) – model danych (skan, podstrona, problem, wyniki fokusu i deklaracji), migracje Alembic. Opis: [docs/model-danych.md](docs/model-danych.md).
- **Skan** (`src/audytor/skan`) – komenda `audytor-scan`: render → axe-core → zapis wyniku; lista podstron i limit tempa dla workera. Instrukcja: [docs/audyt-axe.md](docs/audyt-axe.md).
- **REST API** (`src/audytor/api`) – FastAPI: `/health`, zlecenie skanu, status, wyniki. Opis: [docs/backend.md](docs/backend.md).
- **Worker** (`src/audytor/worker`) – Celery: wykonuje skany zlecone przez API i zapisuje wyniki w bazie.
- **Deklaracja dostępności** (`src/audytor/deklaracja`) – wykrywanie linku do deklaracji (F17), wymogi do walidacji (F18). Instrukcja: [docs/deklaracja.md](docs/deklaracja.md), checklista: [docs/deklaracja-checklista.md](docs/deklaracja-checklista.md).
- **Test fokusu** (`src/audytor/fokus`) – przejście stroną klawiszem Tab i ocena widoczności fokusu (WCAG 2.4.7). Instrukcja i wybór modelu wizyjnego: [docs/ai-wizja-fokus.md](docs/ai-wizja-fokus.md).

## Dokumentacja

- [Backend: API, worker, docker-compose, CI](docs/backend.md)
- [Kontrakt danych między modułami](docs/kontrakt-danych.md)
- [Model danych (ERD)](docs/model-danych.md)
- [Audyt axe-core i skan wielu podstron (F6)](docs/audyt-axe.md)
- [Rozpoznanie: audyt dostępności PDF](docs/rozpoznanie-pdf.md)
- [Konwencje i zasady współpracy](docs/konwencje.md)
- [AI: ocena tekstu alternatywnego (F9)](docs/ai-ocena-alt.md)
- [AI: model wizyjny i test fokusu (F8)](docs/ai-wizja-fokus.md)
- [Deklaracja dostępności: wyszukiwanie i checklista (F17, F18)](docs/deklaracja.md)
