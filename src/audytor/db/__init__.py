"""Baza danych wyników (osoba 2 + osoba 6): model danych v1 i zapis wyników.

Publiczne API:
    Skan, Podstrona, Problem, StatusSkanu – modele SQLAlchemy (models.py)
    otworz_baze(url)                      – połączenie + fabryka sesji (zapis.py)
    zapisz_skan / zapisz_podstrone        – zapis wyników w formacie z kontraktu
    wynik_podstrony(podstrona)            – odczyt z bazy z powrotem do formatu wynik.json
Opis modelu i diagram ERD: docs/model-danych.md.
"""

from .models import Base, Podstrona, Problem, Skan, StatusSkanu
from .zapis import otworz_baze, utworz_tabele, wynik_podstrony, zapisz_podstrone, zapisz_skan

__all__ = [
    "Base",
    "Podstrona",
    "Problem",
    "Skan",
    "StatusSkanu",
    "otworz_baze",
    "utworz_tabele",
    "wynik_podstrony",
    "zapisz_podstrone",
    "zapisz_skan",
]
