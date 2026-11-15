"""Uruchamianie axe-core na otwartej stronie Playwrighta (F6).

Użycie razem z crawlerem (strona po wyrenderowaniu JS i zamknięciu banera cookies):

    from audytor.crawler import Renderer
    from audytor.axe import uruchom_axe, axe_na_problemy

    with Renderer() as renderer:
        with renderer.open("https://www.gov.pl/") as opened:
            wynik_axe = uruchom_axe(opened.page)
            problemy = axe_na_problemy(wynik_axe, opened.final_url)
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from playwright.sync_api import Page

# Sprawdzamy tylko reguły przypisane do WCAG 2.0/2.1 na poziomach A i AA (zakres projektu).
# Reguły "best-practice" i WCAG 2.2 można dodać później, rozszerzając tę listę.
DOMYSLNE_TAGI = ("wcag2a", "wcag2aa", "wcag21a", "wcag21aa")

# violations – pewne błędy, incomplete – axe nie umie rozstrzygnąć (trafią do weryfikacji).
# Wyników "passes" i "inapplicable" nie potrzebujemy; axe zostawia z nich tylko po 1 elemencie.
TYPY_WYNIKOW = ["violations", "incomplete"]

# Tłumaczenia komunikatów axe-core (opis, pomoc, szczegóły) – patrz locales/README.md.
_KATALOG_TLUMACZEN = Path(__file__).with_name("locales")


class AxeError(Exception):
    """axe-core nie dał się uruchomić na stronie."""


@lru_cache(maxsize=1)
def _skrypt_axe() -> str:
    # Skrypt axe-core dostarcza pakiet axe-playwright-python – nie trzymamy własnej kopii.
    from axe_playwright_python.sync_playwright import Axe

    return Axe().axe_script


@lru_cache(maxsize=None)
def _tlumaczenie(jezyk: str) -> dict:
    sciezka = _KATALOG_TLUMACZEN / f"{jezyk}.json"
    if not sciezka.is_file():
        raise ValueError(f"Brak tłumaczenia axe-core dla języka {jezyk!r} (w {_KATALOG_TLUMACZEN})")
    return json.loads(sciezka.read_text(encoding="utf-8"))


def wersja_axe() -> str:
    """Wersja dołączonego axe-core, np. "4.12.1" (do metadanych wyniku)."""
    naglowek = _skrypt_axe()[:200]
    for slowo in naglowek.split():
        if slowo.startswith("v") and slowo[1:2].isdigit():
            return slowo[1:]
    return "nieznana"


def uruchom_axe(
    page: Page,
    tagi: tuple[str, ...] | list[str] = DOMYSLNE_TAGI,
    kontekst=None,
    jezyk: str | None = "pl",
) -> dict:
    """Wstrzykuje axe-core do strony, uruchamia audyt i zwraca surowy wynik (słownik jak z `axe.run()`).

    `tagi` – zestaw reguł (tagi axe), domyślnie WCAG 2.0/2.1 A i AA.
    `kontekst` – opcjonalnie fragment strony do sprawdzenia (selektor CSS lub obiekt kontekstu axe).
    `jezyk` – język komunikatów (domyślnie polski); None = oryginalne komunikaty angielskie.

    Ograniczenie: sprawdzana jest główna ramka strony; treść w <iframe> nie jest jeszcze audytowana.
    """
    opcje = {"runOnly": {"type": "tag", "values": list(tagi)}, "resultTypes": TYPY_WYNIKOW}
    try:
        page.evaluate(_skrypt_axe())
        if jezyk:
            page.evaluate("(locale) => axe.configure({ locale })", _tlumaczenie(jezyk))
        return page.evaluate(
            "([kontekst, opcje]) => axe.run(kontekst ?? document, opcje)",
            [kontekst, opcje],
        )
    except Exception as exc:  # błędy Playwrighta i wyjątki z axe w przeglądarce
        pierwsza_linia = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        raise AxeError(f"Nie udało się uruchomić axe-core na {page.url}: {pierwsza_linia}") from exc
