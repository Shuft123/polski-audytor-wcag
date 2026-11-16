# Backend: API, worker, docker-compose, CI

Osoba 6, sprint 1 (F21 – szkielet API, F28 – repozytorium, CI, docker-compose). Szkielet łączy moduły
kolegów w jedną usługę: crawler (osoba 1) i axe-core (osoba 2) uruchamia worker, wyniki trafiają do bazy
w modelu danych v1 (osoba 2), a API je udostępnia w formacie z [kontraktu](kontrakt-danych.md).

## Architektura

```mermaid
flowchart LR
    K[Klient<br/>curl / Swagger / dashboard] -- "POST /skany" --> API[API<br/>FastAPI]
    API -- "skan: oczekuje" --> DB[(PostgreSQL)]
    API -- "zadanie audytor.skanuj_strone(id)" --> R[(Redis)]
    R --> W[Worker Celery]
    W -- "render + axe-core<br/>(audytor.skan.skanuj_strone)" --> S[Strona WWW]
    W -- "podstrona + problemy,<br/>status: zakonczony / blad" --> DB
    W -- "migawka + wynik.json" --> V[/wolumen wyniki/]
    K -- "GET /skany/{id}, /wyniki" --> API
```

Stan skanu jest w tabeli `skan` (nie w Celery): `oczekuje` → `w_trakcie` → `zakonczony` albo `blad`
(z `opis_bledu`). Sprint 1 skanuje jedną stronę – `url_startowy`. Wiele podstron (F1) i pełna kolejka
(F4, ponawianie, limity) – sprint 3, w tym samym zadaniu workera (`src/audytor/worker/zadania.py`).

## Endpointy

Pełny opis z przykładami: http://localhost:8000/docs (Swagger) albo `/openapi.json`.

| Metoda i ścieżka | Odpowiedź | Opis |
|---|---|---|
| `GET /health` | 200 / 503 | `{"status", "wersja", "baza", "kolejka"}`. 503, gdy baza lub Redis nie działa albo brak tabel (wtedy `baza` podpowiada `alembic upgrade head`). |
| `POST /skany` | 202 | Body: `{"url": "https://...", "parametry": {}}`. Adres jest normalizowany jak w crawlerze; nie-HTTP(S) → 422. Odpowiedź: skan ze statusem `oczekuje`, nagłówek `Location`. Gdy Redis nie działa → 503, a skan dostaje status `blad`. |
| `GET /skany?limit=20` | 200 | Ostatnie skany, od najnowszego. |
| `GET /skany/{id}` | 200 / 404 | Status skanu, czasy (UTC), `opis_bledu`, `liczba_podstron`, `liczba_problemow`. |
| `GET /skany/{id}/wyniki` | 200 / 404 | `{"skan": ..., "podstrony": [wynik.json, ...]}` – każda podstrona w formacie `WynikStrony` (kontrakt, sekcja 2), razem z `podsumowanie`. Pusta lista, dopóki skan trwa. |

## Zmienne środowiskowe

Czyta je `src/audytor/ustawienia.py` (API, worker, Alembic). Wzór: `.env.example`.

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `AUDYTOR_DB_URL` | `sqlite:///audytor.db` | Baza (SQLAlchemy). W Dockerze `postgresql+psycopg://audytor:audytor@postgres:5432/audytor`. |
| `AUDYTOR_REDIS_URL` | `redis://localhost:6379/0` | Broker Celery. |
| `AUDYTOR_WYNIKI_DIR` | `wyniki` | Migawki i `wynik.json` – `skan-<id>/<strona>/`. |
| `AUDYTOR_PRZEGLADARKA` | (puste) | `chrome` / `msedge` – przeglądarka z systemu zamiast Chromium z Playwrighta. |
| `AUDYTOR_TIMEOUT_S` | `30` | Limit wczytania strony. |

## Praca bez Dockera

Potrzebne: PostgreSQL (albo SQLite – domyślnie) i Redis. Najprościej postawić tylko je z compose:

```
docker compose up -d postgres redis
set AUDYTOR_DB_URL=postgresql+psycopg://audytor:audytor@localhost:5432/audytor     # PowerShell: $env:AUDYTOR_DB_URL="..."
alembic upgrade head
audytor-api --reload                                   # terminal 1: http://localhost:8000/docs
celery -A audytor.worker worker --loglevel=info --pool=solo   # terminal 2 (na Windows --pool=solo)
```

Celery na Windows nie obsługuje domyślnej puli procesów – stąd `--pool=solo`. W Dockerze to nie jest potrzebne.

## Migracje bazy (Alembic)

Tabele tworzy `alembic upgrade head` (w Dockerze robi to usługa `migracje` przed startem API i workera).
API i worker **nie** tworzą tabel same. `audytor-scan --db` dalej używa `create_all` – wygodne do
szybkich testów na SQLite, ale nie mieszaj tego z migracjami na tej samej bazie.

Zmiana modelu (`src/audytor/db/models.py`):

```
alembic revision --autogenerate -m "krótki opis zmiany"    # na bazie z aktualnymi migracjami
# przejrzyj wygenerowany plik w migrations/versions/ (autogenerate nie widzi np. zmian CHECK)
alembic upgrade head
```

CI uruchamia `alembic check` na PostgreSQL i test `tests/db/test_migracje.py` na SQLite – gdy model
zmieni się bez migracji, PR się nie zmerguje.

## CI (`.github/workflows/ci.yml`)

Przy każdym PR do `main` i po merge'u:

| Zadanie | Co robi |
|---|---|
| `lint` | `ruff check .` (reguły E, F, W; linia do 120 znaków – `pyproject.toml`). |
| `testy` | `pytest` z zainstalowanym Chromium – także testy `browser` (lokalny serwer HTTP, bez internetu). |
| `migracje (PostgreSQL)` | `alembic upgrade head`, `alembic check`, downgrade i ponowny upgrade na prawdziwym PostgreSQL. |
| `docker-compose (skan przez API)` | Buduje obraz, startuje całość, sprawdza `/health` i wykonuje skan `https://example.com/` przez API. |

## Znane ograniczenia (sprint 1)

- Worker uruchamia przeglądarkę dla każdego skanu (ok. 1–2 s narzutu). Przy wielu podstronach (sprint 3)
  warto trzymać jeden `Renderer` na proces workera.
- Brak uwierzytelniania API – usługa ma działać lokalnie / w sieci zespołu. Do ustalenia przed pilotażem.
- Wyniki (migawki) w wolumenie Dockera `wyniki`; podgląd: `docker compose cp worker:/app/wyniki ./wyniki-z-dockera`.
