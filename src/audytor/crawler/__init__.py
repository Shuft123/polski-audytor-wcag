"""Moduł crawlera (osoba 1): renderowanie stron, migawki, linki wewnętrzne, robots.txt.

Publiczne API dla innych modułów:
    Renderer, RenderOptions   – renderowanie strony (render.py)
    PageSnapshot, save_snapshot, load_meta – migawka i jej zapis (snapshot.py)
    classify_links, normalize_url – linki (links.py)
"""

from .links import LinkSet, classify_links, is_internal, normalize_url
from .snapshot import PageSnapshot, add_base_href, load_meta, save_snapshot, slug_for_url

__all__ = [
    "LinkSet",
    "PageSnapshot",
    "RenderError",
    "RenderOptions",
    "Renderer",
    "RobotsDisallowedError",
    "add_base_href",
    "classify_links",
    "is_internal",
    "load_meta",
    "normalize_url",
    "save_snapshot",
    "slug_for_url",
]


def __getattr__(name: str):
    # Renderer wymaga Playwrighta – importujemy go dopiero, gdy jest potrzebny,
    # żeby testy linków i robots.txt działały bez przeglądarki.
    if name in {"Renderer", "RenderOptions", "RenderError", "RobotsDisallowedError"}:
        from . import render

        return getattr(render, name)
    raise AttributeError(name)
