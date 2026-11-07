"""Audyt automatyczny axe-core (osoba 2, F6/F7).

Publiczne API:
    uruchom_axe(page)              – audyt otwartej strony Playwrighta, surowy wynik axe (uruchom.py)
    axe_na_problemy(wynik, url)    – zamiana wyniku axe na wspólny format `Problem` (mapowanie.py)
    wersja_axe()                   – wersja dołączonego axe-core
"""

from .mapowanie import axe_na_problemy, kryteria_z_tagow, poziom_z_tagow, selektor_z_target

__all__ = [
    "AxeError",
    "DOMYSLNE_TAGI",
    "axe_na_problemy",
    "kryteria_z_tagow",
    "poziom_z_tagow",
    "selektor_z_target",
    "uruchom_axe",
    "wersja_axe",
]


def __getattr__(name: str):
    # uruchom.py wymaga Playwrighta – importujemy go dopiero, gdy jest potrzebny,
    # żeby mapowanie (i jego testy) działało bez przeglądarki. Tak samo jak w audytor.crawler.
    if name in {"uruchom_axe", "wersja_axe", "AxeError", "DOMYSLNE_TAGI"}:
        from . import uruchom

        return getattr(uruchom, name)
    raise AttributeError(name)
