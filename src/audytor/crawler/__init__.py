"""Moduł crawlera (osoba 1): renderowanie stron, migawki, linki wewnętrzne, robots.txt.

Publiczne API dla innych modułów:
    Renderer, RenderOptions   – renderowanie strony (render.py)
    PageSnapshot, save_snapshot, load_meta – migawka i jej zapis (snapshot.py)
    classify_links, normalize_url – linki (links.py)
    SiteCrawler, CrawlOptions, CrawlResult, load_crawl – crawling wielu podstron (crawl.py, sprint 2)
"""

from .links import LinkSet, classify_links, is_internal, normalize_url, strip_tracking
from .snapshot import PageSnapshot, add_base_href, load_meta, save_snapshot, slug_for_url

__all__ = [
    "CrawlOptions",
    "CrawlResult",
    "LinkSet",
    "PageSnapshot",
    "RenderError",
    "RenderOptions",
    "Renderer",
    "RobotsDisallowedError",
    "SiteCrawler",
    "add_base_href",
    "classify_links",
    "is_internal",
    "load_crawl",
    "load_meta",
    "normalize_url",
    "save_snapshot",
    "slug_for_url",
    "strip_tracking",
]


def __getattr__(name: str):
    # Renderer wymaga Playwrighta – importujemy go dopiero, gdy jest potrzebny,
    # żeby testy linków i robots.txt działały bez przeglądarki.
    if name in {"Renderer", "RenderOptions", "RenderError", "RobotsDisallowedError"}:
        from . import render

        return getattr(render, name)
    if name in {"SiteCrawler", "CrawlOptions", "CrawlResult", "load_crawl"}:
        from . import crawl

        return getattr(crawl, name)
    raise AttributeError(name)
