"""Przebieg skanu (sprint 1): adres -> render (crawler) -> axe-core -> migawka + wynik.json.

Publiczne API:
    skanuj_strone(renderer, url, out_dir) – skan jednej strony (przebieg.py)
Wiersz poleceń: `audytor-scan URL` albo `python -m audytor.skan URL` (cli.py).
"""

from .przebieg import SkanError, skanuj_strone

__all__ = ["SkanError", "skanuj_strone"]
