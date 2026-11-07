"""Wspólny format wyników audytu (F7) – używają go axe-core (osoba 2), moduły AI (osoby 3 i 4),
deklaracja dostępności (osoba 5), baza danych i raporty (osoba 6).

Opis formatu: docs/kontrakt-danych.md, sekcja 2.

Publiczne API:
    Problem                     – jeden wykryty problem (z axe albo z AI)
    WynikStrony                 – wszystkie problemy jednej podstrony + metadane skanu
    Zrodlo, Waga, Status        – dozwolone wartości pól
    zapisz_wynik, wczytaj_wynik – zapis / odczyt pliku wynik.json
"""

from .format import (
    SCHEMA_VERSION,
    WYNIK_FILE,
    Problem,
    Status,
    Waga,
    WynikStrony,
    Zrodlo,
    teraz_utc,
    wczytaj_wynik,
    zapisz_wynik,
)

__all__ = [
    "SCHEMA_VERSION",
    "WYNIK_FILE",
    "Problem",
    "Status",
    "Waga",
    "WynikStrony",
    "Zrodlo",
    "teraz_utc",
    "wczytaj_wynik",
    "zapisz_wynik",
]
