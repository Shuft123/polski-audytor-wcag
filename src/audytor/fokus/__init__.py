"""Test widoczności fokusu (osoba 4, F8, WCAG 2.4.7).

Publiczne API:
    przejdz_tabem(page, ...) -> WynikFokusu   – przejście stroną klawiszem Tab z porównaniem zrzutów
    mapa_fokusu(page, wynik) -> Image          – zrzut strony z ponumerowaną kolejnością fokusu
    zmierz(bez, z, w, h) -> PomiarFokusu       – porównanie dwóch wycinków (bez przeglądarki)
"""

from .pomiar import PomiarFokusu, kontrast, luminancja, obraz_porownania, zmierz

__all__ = [
    "KrokFokusu",
    "PomiarFokusu",
    "WynikFokusu",
    "kontrast",
    "luminancja",
    "mapa_fokusu",
    "obraz_porownania",
    "przejdz_tabem",
    "zmierz",
]


def __getattr__(name: str):
    # Część z Playwrightem ładujemy leniwie (jak w module crawlera).
    if name in {"KrokFokusu", "WynikFokusu", "mapa_fokusu", "przejdz_tabem"}:
        from . import tab

        return getattr(tab, name)
    raise AttributeError(name)
