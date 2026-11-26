# Model danych (v1 + sprint 2)

Model danych wyników audytu (F7; sprint 1, rozszerzony w sprincie 2 – migracja 0002). Kod: `src/audytor/db/models.py`, format wymiany między
modułami: [kontrakt-danych.md](kontrakt-danych.md), sekcja 2.

## Diagram ERD

```mermaid
erDiagram
    SKAN ||--o{ PODSTRONA : "zawiera"
    PODSTRONA ||--o{ PROBLEM : "ma"
    PODSTRONA ||--o| WYNIK_FOKUSU : "test fokusu"
    SKAN ||--o| WYNIK_DEKLARACJI : "deklaracja witryny"

    SKAN {
        int id PK
        string url_startowy
        string status "oczekuje | w_trakcie | zakonczony | blad"
        timestamptz utworzono
        timestamptz rozpoczeto "NULL"
        timestamptz zakonczono "NULL"
        text opis_bledu "NULL"
        jsonb parametry "limity, opcje crawlera"
    }

    PODSTRONA {
        int id PK
        int skan_id FK
        string url "final_url, unikalny w skanie"
        string requested_url
        int http_status "NULL"
        timestamptz sprawdzono
        string migawka "folder migawki, NULL"
        jsonb narzedzia "wersje axe-core, audytora, modeli AI"
        jsonb ostrzezenia
        text blad "NULL = sprawdzona; inaczej powód (sprint 2)"
    }

    PROBLEM {
        int id PK
        int podstrona_id FK
        string klucz "stały id z wynik.json, unikalny w podstronie"
        string zrodlo "axe | ai | heurystyka"
        string regula "np. image-alt, ai-alt-tekst"
        jsonb kryteria_wcag "np. 1.1.1"
        string poziom_wcag "A | AA | AAA, NULL"
        string status "blad | do_weryfikacji | odrzucony"
        string waga "krytyczna | powazna | umiarkowana | drobna, NULL"
        text selektor
        text fragment_html
        text opis
        text szczegoly
        string link_pomocy "NULL"
        float poziom_pewnosci "0-1, NULL"
        text uzasadnienie "NULL, dla AI"
        timestamptz wykryto
    }

    WYNIK_FOKUSU {
        int id PK
        int podstrona_id FK "unikalny – jeden test na podstronę"
        timestamptz sprawdzono
        text zakonczenie "dlaczego przestano naciskać Tab"
        int limit_krokow "NULL"
        jsonb podsumowanie "liczby kroków wg werdyktu"
        jsonb kroki "kolejne elementy z fokusem"
        jsonb ostrzezenia
        string mapa "plik mapy fokusu, NULL"
    }

    WYNIK_DEKLARACJI {
        int id PK
        int skan_id FK "unikalny – jedna deklaracja na skan"
        timestamptz sprawdzono
        bool znaleziono
        string url_deklaracji "NULL"
        string metoda "link | meta | typowy_adres | brak"
        string status "zweryfikowana | bez_a11y | niezweryfikowana | brak"
        float pewnosc
        bool zweryfikowano
        jsonb identyfikatory_a11y
        jsonb brakujace_identyfikatory
        jsonb kandydaci
        jsonb ostrzezenia
        jsonb walidacja "F18 v1, NULL"
    }
```

## Tabele

| Tabela | Co przechowuje | Uwagi |
|---|---|---|
| `skan` | Jedno zlecenie skanu witryny. | `status` to statusy kolejki z F4. `parametry` – opcje, z jakimi skan uruchomiono (głębokość, limit stron itd.). |
| `podstrona` | Jedna podstrona w skanie. | Odpowiada plikowi `wynik.json` bez listy problemów. `url` = `final_url` z migawki. `blad` (sprint 2) – podstrony nie udało się sprawdzić (robots.txt, timeout); wtedy nie ma problemów. |
| `problem` | Jeden wykryty problem (axe, AI albo heurystyka). | Pola 1:1 z `Problem` z kontraktu (sekcja 2). `klucz` = pole `id` z `wynik.json`. |
| `wynik_fokusu` | Pełny wynik testu fokusu podstrony (F8, osoba 4). | Sprint 2. 1:1 z podstroną. Problemy z testu są **też** w tabeli `problem` (`zrodlo = "heurystyka"`); tu zostają kroki Tab i podsumowanie – do mapy fokusu w raporcie. |
| `wynik_deklaracji` | Wynik wyszukania (F17) i walidacji (F18) deklaracji dostępności (osoba 5). | Sprint 2. 1:1 ze skanem – deklaracja dotyczy witryny, nie podstrony. `walidacja` – miejsce na wynik walidatora v1 (format ustala osoba 5). |

## Decyzje projektowe

- **Wspólna tabela problemów dla axe, AI i heurystyk.** Wyniki mają ten sam kształt; różni je tylko `zrodlo`,
  a pola specyficzne dla AI (`poziom_pewnosci`, `uzasadnienie`) dla axe zostają puste lub mają stałą wartość.
- **Źródło „heurystyka” (sprint 2)** – reguły bez modelu AI (test fokusu, deklaracja, tryb AI bez modelu)
  nie udają wyników AI. Uzasadnienie i zasady: [kontrakt danych, sekcja 2.4](kontrakt-danych.md).
- **Fokus i deklaracja w osobnych tabelach (sprint 2)** – ich pełne wyniki (kroki, kandydaci, identyfikatory
  a11y-*) nie są listą problemów. Problemy, które z nich wynikają, i tak trafiają do `problem`, więc raport
  i API liczą je razem z axe. Szczegóły jako JSON – format należy do modułów osób 4 i 5 i może się zmieniać
  bez migracji; kolumny dostały tylko pola, po których będziemy filtrować (status, znaleziono, pewność).
- **Niesprawdzona podstrona to wiersz z `blad`, a nie brak wiersza (sprint 2)** – w skanie wielu podstron
  widać, które się nie udały i dlaczego; „0 problemów” nie myli się z „nie sprawdzono”.
- **Wartości wyliczeniowe jako tekst z ograniczeniem CHECK**, a nie natywny `ENUM` PostgreSQL – nowa
  wartość (np. status `poprawiony`) nie wymaga `ALTER TYPE`.
- **Listy jako JSON** (`kryteria_wcag`, `ostrzezenia`), w PostgreSQL jako `JSONB`. Wyszukiwanie problemów
  dla kryterium: `WHERE kryteria_wcag ? '1.1.1'`. Jeśli raporty będą często grupować po kryterium,
  można to później rozbić na tabelę `problem_kryterium`.
- **Stały `klucz` problemu** (skrót z adresu, źródła, reguły i selektora) – ten sam problem w kolejnym skanie
  ma ten sam klucz. Przyda się do wykrywania zmian między skanami (F5) i do cache wyników AI (F15).
- **Usuwanie kaskadowe:** usunięcie skanu usuwa jego podstrony, problemy, wyniki fokusu i deklaracji.
- **Czasy w UTC** (`timestamptz`), jak `fetched_at` w migawkach.

## Użycie

```python
from audytor.db import otworz_baze, zapisz_skan, wynik_podstrony
from audytor.wyniki import wczytaj_wynik

sesje = otworz_baze("sqlite:///audytor.db")   # docelowo: postgresql+psycopg://...
with sesje() as sesja:
    skan = zapisz_skan(sesja, [wczytaj_wynik("wyniki/gov-pl")], url_startowy="https://www.gov.pl/")
    sesja.commit()
    wynik = wynik_podstrony(skan.podstrony[0])   # z powrotem w formacie wynik.json (np. dla API)
```

Z wiersza poleceń: `audytor-scan https://www.gov.pl/ --db sqlite:///audytor.db`.

Wyniki fokusu i deklaracji (sprint 2) – funkcje przyjmują słowniki z `to_dict()` modułów osób 4 i 5:

```python
from audytor.db import zapisz_wynik_fokusu, zapisz_wynik_deklaracji, wynik_fokusu_dict, wynik_deklaracji_dict

zapisz_wynik_fokusu(sesja, podstrona, wynik_fokusu.to_dict(), limit_krokow=60, mapa="mapa-fokusu.jpg")
zapisz_wynik_deklaracji(sesja, skan, wynik_deklaracji.to_dict())
sesja.commit()
wynik_fokusu_dict(podstrona), wynik_deklaracji_dict(skan)     # odczyt dla API i raportu (None = nie sprawdzano)
```

## Migracje (z osobą 6)

- **Migracje Alembic** – `0001_model_danych_v1.py` (sprint 1) i `0002_fokus_deklaracja_heurystyka.py`
  (sprint 2: tabele `wynik_fokusu`, `wynik_deklaracji`, kolumna `podstrona.blad`, źródło „heurystyka”;
  downgrade zamienia „heurystyka” z powrotem na „ai”). Razem odtwarzają dokładnie te tabele
  (sprawdza to `alembic check` w CI na PostgreSQL). Tabele w PostgreSQL tworzy `alembic upgrade head`
  (w docker-compose – usługa `migracje`); API i worker nie wywołują `create_all`. `otworz_baze()` z
  `utworz=True` zostaje dla `audytor-scan --db` i testów na SQLite. Jak dodać migrację: [backend.md](backend.md#migracje-bazy-alembic).
- **Sterownik PostgreSQL** – `psycopg[binary]` w zależnościach, adres bazy z docker-compose:
  `postgresql+psycopg://audytor:audytor@localhost:5432/audytor`.
