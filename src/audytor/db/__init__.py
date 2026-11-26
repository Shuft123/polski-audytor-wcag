"""Baza danych wyników (osoba 2 + osoba 6): model danych v1 i zapis wyników.

Publiczne API:
    Skan, Podstrona, Problem, StatusSkanu – modele SQLAlchemy (models.py)
    otworz_baze(url)                      – połączenie + fabryka sesji (zapis.py)
    zapisz_skan / zapisz_podstrone        – zapis wyników w formacie z kontraktu
    wynik_podstrony(podstrona)            – odczyt z bazy z powrotem do formatu wynik.json
    zapisz_wynik_fokusu / zapisz_wynik_deklaracji – wyniki fokusu (F8) i deklaracji (F17/F18), sprint 2
    wynik_fokusu_dict / wynik_deklaracji_dict      – ich odczyt dla API i raportu
Opis modelu i diagram ERD: docs/model-danych.md.
"""

from .models import Base, Podstrona, Problem, Skan, StatusSkanu, WynikDeklaracji, WynikFokusu
from .zapis import (
    otworz_baze,
    utworz_tabele,
    wynik_deklaracji_dict,
    wynik_fokusu_dict,
    wynik_podstrony,
    zapisz_podstrone,
    zapisz_skan,
    zapisz_wynik_deklaracji,
    zapisz_wynik_fokusu,
)

__all__ = [
    "Base",
    "Podstrona",
    "Problem",
    "Skan",
    "StatusSkanu",
    "WynikDeklaracji",
    "WynikFokusu",
    "otworz_baze",
    "utworz_tabele",
    "wynik_deklaracji_dict",
    "wynik_fokusu_dict",
    "wynik_podstrony",
    "zapisz_podstrone",
    "zapisz_skan",
    "zapisz_wynik_deklaracji",
    "zapisz_wynik_fokusu",
]
