"""Zamiana surowego wyniku axe-core na wspólny format `Problem` (F7).

Zasady (docs/kontrakt-danych.md, sekcja 2.3):
  - jeden element strony (`node`) w wyniku axe = jeden `Problem`;
  - `violations` -> status "blad", poziom pewności 1.0;
  - `incomplete` (axe nie umie rozstrzygnąć) -> status "do_weryfikacji", poziom pewności None;
  - tag `wcag111` -> kryterium "1.1.1", tagi `wcag2a`/`wcag21aa`... -> poziom "A"/"AA";
  - `impact` (critical/serious/moderate/minor) -> waga (krytyczna/powazna/umiarkowana/drobna).

Ten moduł nie wymaga przeglądarki – działa na słowniku z wynikiem axe (np. wczytanym z JSON).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from audytor.wyniki import Problem, Status, Waga, Zrodlo, teraz_utc

_TAG_KRYTERIUM = re.compile(r"^wcag([1-4])(\d)(\d{1,2})$")
_TAG_POZIOM = re.compile(r"^wcag2\d?(a{1,3})$")

WAGA_Z_IMPACT = {
    "critical": Waga.KRYTYCZNA,
    "serious": Waga.POWAZNA,
    "moderate": Waga.UMIARKOWANA,
    "minor": Waga.DROBNA,
}

# Separator części selektora, gdy element leży w iframe albo shadow DOM
# (axe zwraca wtedy listę selektorów: [ramka, element w ramce]).
SEPARATOR_SELEKTORA = " >>> "


def kryteria_z_tagow(tagi: list[str]) -> list[str]:
    """['wcag2a', 'wcag111', 'wcag412'] -> ['1.1.1', '4.1.2'] (bez duplikatów, w kolejności)."""
    kryteria: list[str] = []
    for tag in tagi:
        m = _TAG_KRYTERIUM.match(tag)
        if m:
            kryterium = ".".join(m.groups())
            if kryterium not in kryteria:
                kryteria.append(kryterium)
    return kryteria


def poziom_z_tagow(tagi: list[str]) -> str | None:
    """Najniższy (najważniejszy) poziom WCAG z tagów: wcag2a -> "A", wcag21aa -> "AA"."""
    poziomy = []
    for tag in tagi:
        m = _TAG_POZIOM.match(tag)
        if m:
            poziomy.append(m.group(1).upper())
    return min(poziomy, key=len) if poziomy else None


def selektor_z_target(target: Any) -> str:
    """Target z axe -> jeden napis.

    Zwykle ['#id']. Element w iframe: ['iframe#mapa', 'button'] (kolejne ramki).
    Element w shadow DOM: [['moj-komponent', 'button']] (host, potem element w jego shadow root).
    Kolejne poziomy łączymy separatorem ' >>> '.
    """
    if isinstance(target, str):
        return target
    if not target:
        return ""
    czesci: list[str] = []
    for czesc in target:
        if isinstance(czesc, str):
            czesci.append(czesc)
        else:
            czesci.extend(map(str, czesc))
    return SEPARATOR_SELEKTORA.join(czesci)


def _czas_iso(czas: str | None) -> str:
    """Czas z axe ("2026-11-07T12:04:04.987Z") -> format z kontraktu ("2026-11-07T12:04:04+00:00")."""
    if not czas:
        return teraz_utc()
    try:
        dt = datetime.fromisoformat(czas)
    except ValueError:
        return teraz_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _waga(impact: str | None) -> str | None:
    return WAGA_Z_IMPACT[impact].value if impact in WAGA_Z_IMPACT else None


def _problemy_z_reguly(regula: dict, url: str, status: Status, wykryto: str) -> list[Problem]:
    tagi = regula.get("tags", [])
    kryteria = kryteria_z_tagow(tagi)
    poziom = poziom_z_tagow(tagi)
    problemy = []
    for node in regula.get("nodes", []):
        problemy.append(
            Problem(
                url_podstrony=url,
                zrodlo=Zrodlo.AXE,
                regula=regula["id"],
                kryteria_wcag=kryteria,
                status=status,
                selektor=selektor_z_target(node.get("target")),
                fragment_html=node.get("html") or "",
                waga=_waga(node.get("impact") or regula.get("impact")),
                poziom_wcag=poziom,
                opis=regula.get("help", ""),
                szczegoly=(node.get("failureSummary") or regula.get("description", "")).strip(),
                link_pomocy=regula.get("helpUrl"),
                poziom_pewnosci=1.0 if status == Status.BLAD else None,
                wykryto=wykryto,
            )
        )
    return problemy


def axe_na_problemy(wynik_axe: dict, url: str | None = None, wykryto: str | None = None) -> list[Problem]:
    """Surowy wynik `axe.run()` -> lista problemów we wspólnym formacie.

    `url` – adres podstrony (domyślnie `url` z wyniku axe); używamy final_url z migawki.
    Duplikaty (ten sam element zgłoszony przez axe dwa razy) są pomijane.
    """
    url = url or wynik_axe.get("url", "")
    wykryto = wykryto or _czas_iso(wynik_axe.get("timestamp"))
    problemy: list[Problem] = []
    for regula in wynik_axe.get("violations", []):
        problemy += _problemy_z_reguly(regula, url, Status.BLAD, wykryto)
    for regula in wynik_axe.get("incomplete", []):
        problemy += _problemy_z_reguly(regula, url, Status.DO_WERYFIKACJI, wykryto)

    widziane: set[str] = set()
    unikalne = []
    for problem in problemy:
        if problem.id not in widziane:
            widziane.add(problem.id)
            unikalne.append(problem)
    return unikalne
