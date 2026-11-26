"""Przebieg skanu (sprint 1): adres -> render (crawler) -> axe-core -> migawka + wynik.json.

Publiczne API:
    skanuj_strone(renderer, url, out_dir) – skan jednej strony (przebieg.py)
    lista_podstron(url, parametry)        – podstrony do sprawdzenia w skanie (lista.py, sprint 2)
    Ogranicznik                           – limit tempa zapytań na witrynę (lista.py)
Wiersz poleceń: `audytor-scan URL` albo `python -m audytor.skan URL` (cli.py).
"""

from .lista import ListaPodstron, Ogranicznik, lista_podstron
from .przebieg import SkanError, skanuj_strone

__all__ = ["ListaPodstron", "Ogranicznik", "SkanError", "lista_podstron", "skanuj_strone"]
