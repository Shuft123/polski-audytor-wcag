# Konwencje i zasady współpracy

Spisane na podstawie tego, jak zespół faktycznie pracował w sprincie 1 (kod, gałęzie, PR-y).
**Propozycja do zatwierdzenia na przeglądzie sprintu** – zmiany zgłaszamy pull requestem do tego pliku.

## 1. Struktura repozytorium

```
src/audytor/<moduł>/     kod – jeden pakiet na obszar: crawler, axe, wyniki, db, skan, api, worker,
                         a od sprintu 2 m.in. ai, fokus, deklaracja, raport
tests/<moduł>/           testy modułu (pytest); dane testowe w tests/data/ i tests/<moduł>/data/
docs/                    dokumentacja (Markdown, po polsku); docs/wyniki/ – wyniki eksperymentów (CSV)
migrations/              migracje bazy (Alembic) – patrz docs/backend.md
scripts/                 skrypty pomocnicze i pokazowe (nie są częścią pakietu)
notebooks/               notatniki Jupyter / Colab (eksperymenty AI; lint ich nie sprawdza)
.github/                 CI (workflows/ci.yml) i szablon PR
```

- Moduł ma `__init__.py` z opisem publicznego API (zob. `audytor/wyniki`, `audytor/db`), a komendę –
  w `cli.py` + `__main__.py` (`python -m audytor.<moduł>`) i wpis w `[project.scripts]`.
- Wymiana danych między modułami tylko przez formaty z [kontraktu danych](kontrakt-danych.md).
- Nowe zależności dopisujemy do `pyproject.toml` (nie `requirements.txt`). Ciężkie, potrzebne tylko
  jednemu modułowi (np. biblioteki modeli AI) – jako opcjonalna grupa, np. `pip install -e ".[ai]"`.
- Duże pliki (modele, MHTML, PNG) nie trafiają do repo; zrzuty trzymamy jako JPEG.

## 2. Styl kodu i lintery

- Python ≥ 3.11 (CI i Docker: 3.12).
- Linter: **ruff** – `ruff check .` (reguły E, F, W; linia do 120 znaków; konfiguracja w `pyproject.toml`).
  CI odrzuca PR z błędami lintera. Automatyczne poprawki: `ruff check --fix .`.
- Testy: **pytest**. Testy wymagające przeglądarki oznaczamy `@pytest.mark.browser` i pomijamy, gdy jej brak.
  Testy nie mogą zależeć od internetu (lokalny serwer HTTP, migawki z `tests/data/snapshots`).
- Typy w sygnaturach funkcji publicznych, docstring z krótkim opisem po polsku.

## 3. Nazewnictwo gałęzi

- `feature/F<nr>-krotki-opis` – nowa funkcjonalność, np. `feature/F3-crawler`, `feature/F9-ocena-alt`
- `fix/krotki-opis` – poprawka błędu
- `docs/krotki-opis` – tylko dokumentacja
- Małe litery, bez polskich znaków, słowa rozdzielone `-`. Gałąź usuwamy po merge'u.

## 4. Commity

- Format: `F<nr>: co zostało zrobione`, np. `F6, F7: audyt axe-core, format wyników, model danych v1`.
- Po polsku, w trybie dokonanym lub jako rzeczownik; jeden commit = jedna logiczna zmiana.

## 5. Zasady pull requestów i recenzji

- Każde zadanie to zgłoszenie (issue) z numerem funkcjonalności; PR zawiera `Closes #<nr issue>`
  (wypełnij [szablon](../.github/PULL_REQUEST_TEMPLATE.md)). Słowo `Closes` po angielsku – polskie
  „Zamyka” nie zamyka zgłoszenia automatycznie.
- Do `main` wchodzi się **tylko przez PR** – bezpośredni push jest zablokowany regułą `ochrona-main`.
- Wymagane przed merge'em: **zielone CI** i **co najmniej 1 zatwierdzenie** (Approve), w pierwszej
  kolejności od osoby z pary zastępstw: 1↔2, 3↔4, 5↔6.
- Autor merguje sam po zatwierdzeniu (merge commit). Konflikty rozwiązuje autor PR-a: `git merge main`
  na swojej gałęzi.
- PR-y małe i częste – najlepiej jeden na zadanie. Duże pliki wygenerowane (CSV, notatniki) opisujemy w PR.
- Merge zamyka zadanie na tablicy.

## 6. Język

- Nazwy w kodzie (zmienne, funkcje, klasy): **po polsku bez znaków diakrytycznych** (`wynik_strony`,
  `zapisz_skan`) albo po angielsku – konsekwentnie w obrębie modułu (crawler jest po angielsku, reszta po polsku).
  Nazwy pól w formatach wymiany danych – zawsze jak w kontrakcie.
- Komentarze, docstringi, dokumentacja, komunikaty dla użytkownika, opisy PR i commitów: **po polsku**.
