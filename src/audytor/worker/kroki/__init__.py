"""Kroki skanu – punkty podpięcia modułów pod przebieg skanu w workerze (sprint 2).

Worker (`audytor.worker.zadania.wykonaj_skan`) dla każdej podstrony robi render + axe-core, a potem
uruchamia **kroki podstrony**; po wszystkich podstronach – **kroki skanu**. Każdy moduł ma swój plik
i edytuje tylko go – dzięki temu równoległe PR-y nie kolidują:

| Plik            | Osoba | Krok                         | Rodzaj   | Wynik zapisywany w bazie                  |
|-----------------|-------|------------------------------|----------|-------------------------------------------|
| `alt.py`        | 3     | ocena tekstu alternatywnego  | podstrona| problemy (`ctx.dodaj_problemy`)           |
| `fokus.py`      | 4     | test widoczności fokusu      | podstrona| `ctx.fokus` → tabela `wynik_fokusu`       |
| `deklaracja.py` | 5     | wykrycie i walidacja deklar. | skan     | `ctx.deklaracja` → tabela `wynik_deklaracji` |

Zasady (pilnuje ich worker, krok nie musi):
- wyjątek w kroku nie przerywa skanu – trafia do `ostrzezenia` podstrony (albo do logu dla kroku skanu);
- kroki podstrony działają tylko dla podstron sprawdzonych bez błędu i tylko gdy zostało czasu skanu;
- krok można wyłączyć dla jednego skanu: `parametry["pomin_kroki"] = ["fokus", ...]`;
- testy w CI działają bez internetu i bez modelu AI – krok musi mieć tryb bez modelu albo dać się wyłączyć.

Instrukcja: docs/backend.md, sekcja „Jak podpiąć moduł do skanu”.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from audytor.ustawienia import Ustawienia
from audytor.wyniki import Problem, WynikStrony

if TYPE_CHECKING:
    from audytor.crawler.render import OpenedPage

log = logging.getLogger(__name__)

# Otwiera adres we wspólnej przeglądarce skanu – z limitem tempa i robots.txt. Użycie:
#     with ctx.otworz(ctx.url) as opened:     # opened.page – strona Playwrighta, opened.final_url
#         ...
Otwieracz = Callable[[str], AbstractContextManager["OpenedPage"]]

MAX_OSTRZEZENIE = 500
# Nazwy kroków do `parametry["pomin_kroki"]` – stała, żeby API nie importowało modułów kroków (np. modeli AI).
NAZWY_KROKOW = ("alt", "fokus", "deklaracja")


@dataclass
class KontekstPodstrony:
    """Wszystko, czego krok potrzebuje o jednej, już sprawdzonej przez axe-core podstronie."""

    skan_id: int
    wynik: WynikStrony                 # wynik axe-core; kroki dopisują problemy przez dodaj_problemy()
    folder: Path | None                # migawka podstrony: dom.html, screenshot.jpg, meta.json, wynik.json
    jest_startowa: bool                # pierwsza podstrona skanu (url_startowy)
    ustawienia: Ustawienia
    parametry: dict[str, Any]          # parametry skanu z API (POST /skany)
    otworz: Otwieracz                  # ponowne otwarcie strony na żywo (np. test fokusu – Tab po stronie)
    pozostalo_s: Callable[[], float]   # ile sekund zostało z budżetu skanu – krok może skrócić pracę

    # Wyniki wypełniane przez krok fokusu (fokus.py), zapisywane przez worker w tabeli wynik_fokusu:
    fokus: dict[str, Any] | None = None          # WynikFokusu.to_dict()
    fokus_limit_krokow: int | None = None
    fokus_mapa: str | None = None                # ścieżka mapy fokusu względem folderu podstrony

    @property
    def url(self) -> str:
        """Adres podstrony po przekierowaniach (final_url)."""
        return self.wynik.url

    def dodaj_problemy(self, problemy: Iterable[Problem | dict[str, Any]]) -> int:
        """Dopisuje problemy (format wspólny – kontrakt, sekcja 2) do wyniku podstrony. Zwraca liczbę dodanych.

        Słowniki są sprawdzane przez `Problem.from_dict` (źródło, status, kryteria). Problem o `id`
        już obecnym w wyniku jest pomijany, więc krok może bezpiecznie dopisać tę samą listę dwa razy.
        """
        znane = {p.id for p in self.wynik.problemy}
        dodane = 0
        for p in problemy:
            problem = p if isinstance(p, Problem) else Problem.from_dict(p)
            if problem.id not in znane:
                znane.add(problem.id)
                self.wynik.problemy.append(problem)
                dodane += 1
        return dodane


@dataclass
class KontekstSkanu:
    """Kontekst kroku skanu – po sprawdzeniu wszystkich podstron (np. deklaracja dostępności witryny)."""

    skan_id: int
    url_startowy: str
    podstrony: list[WynikStrony]       # podstrony sprawdzone bez błędu, w kolejności skanu
    folder_skanu: Path                 # AUDYTOR_WYNIKI_DIR/skan-<id>
    ustawienia: Ustawienia
    parametry: dict[str, Any]
    otworz: Otwieracz
    pozostalo_s: Callable[[], float]

    # Wynik kroku deklaracji (deklaracja.py), zapisywany przez worker w tabeli wynik_deklaracji:
    deklaracja: dict[str, Any] | None = None     # DeclarationResult.to_dict() (+ opcjonalnie "walidacja")
    deklaracja_sprawdzono: str | None = None     # czas ISO 8601 UTC; None = teraz


@dataclass(frozen=True)
class KrokPodstrony:
    nazwa: str
    funkcja: Callable[[KontekstPodstrony], None]
    tylko_startowa: bool = False       # True = tylko dla strony startowej (krok drogi czasowo)


@dataclass(frozen=True)
class KrokSkanu:
    nazwa: str
    funkcja: Callable[[KontekstSkanu], None]


@dataclass(frozen=True)
class Kroki:
    podstrony: Sequence[KrokPodstrony] = field(default_factory=tuple)
    skanu: Sequence[KrokSkanu] = field(default_factory=tuple)

    def bez(self, pominiete: Iterable[str]) -> Kroki:
        """Te same kroki bez podanych nazw (`parametry["pomin_kroki"]`)."""
        nazwy = set(pominiete)
        return Kroki(
            podstrony=tuple(k for k in self.podstrony if k.nazwa not in nazwy),
            skanu=tuple(k for k in self.skanu if k.nazwa not in nazwy),
        )


def domyslne_kroki() -> Kroki:
    """Kroki uruchamiane w każdym skanie. Kolejność ma znaczenie: alt przed fokusem (fokus jest wolny)."""
    from . import alt, deklaracja, fokus

    return Kroki(podstrony=(alt.KROK, fokus.KROK), skanu=(deklaracja.KROK,))


def _opis(nazwa: str, exc: BaseException) -> str:
    return f"Krok „{nazwa}” nie powiódł się: {str(exc).strip() or type(exc).__name__}"[:MAX_OSTRZEZENIE]


def uruchom_kroki_podstrony(kroki: Iterable[KrokPodstrony], ctx: KontekstPodstrony) -> None:
    for krok in kroki:
        if krok.tylko_startowa and not ctx.jest_startowa:
            continue
        if ctx.pozostalo_s() <= 0:
            ctx.wynik.ostrzezenia.append(f"Krok „{krok.nazwa}” pominięty – przekroczony czas skanu")
            continue
        try:
            krok.funkcja(ctx)
        except Exception as exc:   # krok nie może zepsuć skanu – axe-core i tak jest zapisany
            log.warning("Skan #%s, %s: %s", ctx.skan_id, ctx.url, _opis(krok.nazwa, exc), exc_info=True)
            ctx.wynik.ostrzezenia.append(_opis(krok.nazwa, exc))


def uruchom_kroki_skanu(kroki: Iterable[KrokSkanu], ctx: KontekstSkanu) -> list[str]:
    """Uruchamia kroki skanu. Zwraca opisy błędów (skan i tak kończy się sukcesem)."""
    bledy = []
    for krok in kroki:
        if ctx.pozostalo_s() <= 0:
            bledy.append(f"Krok „{krok.nazwa}” pominięty – przekroczony czas skanu")
            continue
        try:
            krok.funkcja(ctx)
        except Exception as exc:
            log.warning("Skan #%s: %s", ctx.skan_id, _opis(krok.nazwa, exc), exc_info=True)
            bledy.append(_opis(krok.nazwa, exc))
    return bledy


__all__ = [
    "KontekstPodstrony",
    "KontekstSkanu",
    "KrokPodstrony",
    "KrokSkanu",
    "Kroki",
    "NAZWY_KROKOW",
    "Otwieracz",
    "domyslne_kroki",
    "uruchom_kroki_podstrony",
    "uruchom_kroki_skanu",
]
