"""Moduł deklaracji dostępności (osoba 5): wykrywanie (F17), a docelowo walidacja (F18).

Publiczne API dla innych modułów:
    find_in_html(html, page_url)      – kandydaci z DOM strony głównej, bez sieci
    find_declaration(site_url, ...)   – pełne wyszukiwanie z weryfikacją a11y-*
    a11y_ids_in(html)                 – identyfikatory a11y-* na stronie deklaracji
    wymagania                         – checklista wymogów w wersji maszynowej
"""

from . import wymagania
from .wyszukiwanie import (
    Candidate,
    DeclarationResult,
    a11y_ids_in,
    find_candidates,
    find_declaration,
    find_in_html,
)

__all__ = [
    "Candidate",
    "DeclarationResult",
    "a11y_ids_in",
    "find_candidates",
    "find_declaration",
    "find_in_html",
    "wymagania",
]
