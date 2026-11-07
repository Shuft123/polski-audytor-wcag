"""Wspólny format pojedynczego wyniku audytu (F7) i pliku wynik.json.

Każdy wykryty problem – niezależnie od tego, czy znalazł go axe-core, czy model AI – ma ten sam
kształt (`Problem`). Dzięki temu baza danych, API i raport PDF obsługują wszystkie źródła tak samo.
Szczegóły i przykłady: docs/kontrakt-danych.md, sekcja 2.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
WYNIK_FILE = "wynik.json"

# Maksymalna długość fragmentu HTML zapisywanego przy problemie (reszta jest obcinana).
MAX_FRAGMENT_HTML = 2000

_KRYTERIUM_RE = re.compile(r"^[1-4]\.\d{1,2}\.\d{1,2}$")


class Zrodlo(StrEnum):
    """Kto wykrył problem."""

    AXE = "axe"
    AI = "ai"


class Waga(StrEnum):
    """Wpływ problemu na użytkownika (odpowiedniki `impact` z axe-core)."""

    KRYTYCZNA = "krytyczna"     # axe: critical – blokuje dostęp do treści
    POWAZNA = "powazna"         # axe: serious
    UMIARKOWANA = "umiarkowana"  # axe: moderate
    DROBNA = "drobna"           # axe: minor


class Status(StrEnum):
    """Stan problemu w procesie audytu."""

    BLAD = "blad"                      # pewny błąd (axe: violation)
    DO_WERYFIKACJI = "do_weryfikacji"  # wymaga oceny człowieka (axe: incomplete, wszystkie wyniki AI)
    ODRZUCONY = "odrzucony"            # audytor uznał za fałszywy alarm


# Kolejność wag od najpoważniejszej – przydatna do sortowania w raportach.
KOLEJNOSC_WAG = [Waga.KRYTYCZNA, Waga.POWAZNA, Waga.UMIARKOWANA, Waga.DROBNA]


def teraz_utc() -> str:
    """Bieżący czas w formacie ISO 8601 (UTC), jak `fetched_at` w migawkach."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def identyfikator_problemu(url_podstrony: str, zrodlo: str, regula: str, selektor: str) -> str:
    """Stały identyfikator problemu: ten sam problem w kolejnym skanie dostaje ten sam `id`.
    Przyda się do wykrywania zmian między skanami (F5) i do cache wyników AI (F15)."""
    klucz = "\x1f".join([url_podstrony, zrodlo, regula, selektor])
    return hashlib.sha1(klucz.encode("utf-8")).hexdigest()[:16]


@dataclass
class Problem:
    """Jeden wykryty problem dostępności na jednej podstronie."""

    url_podstrony: str                  # final_url z migawki
    zrodlo: str                         # Zrodlo: "axe" | "ai"
    regula: str                         # id reguły axe (np. "image-alt") albo testu AI (np. "ai-alt-tekst")
    kryteria_wcag: list[str]            # np. ["1.1.1"]; reguła może dotyczyć kilku kryteriów
    status: str                         # Status: "blad" | "do_weryfikacji" | "odrzucony"
    selektor: str                       # selektor CSS elementu ("" = cała strona)
    fragment_html: str = ""             # fragment kodu elementu (obcięty do MAX_FRAGMENT_HTML znaków)
    waga: str | None = None             # Waga albo None, gdy źródło jej nie podaje
    poziom_wcag: str | None = None      # "A" | "AA" | "AAA" | None (reguły spoza WCAG)
    opis: str = ""                      # krótki opis problemu
    szczegoly: str = ""                 # co dokładnie jest nie tak / jak poprawić
    link_pomocy: str | None = None      # dokumentacja reguły
    poziom_pewnosci: float | None = None  # 0.0–1.0; axe violation = 1.0, axe incomplete = None
    uzasadnienie: str | None = None     # uzasadnienie modelu AI (dla axe zwykle None)
    wykryto: str = field(default_factory=teraz_utc)
    id: str = ""                        # liczony automatycznie, gdy pusty

    def __post_init__(self) -> None:
        self.zrodlo = Zrodlo(self.zrodlo).value
        self.status = Status(self.status).value
        if self.waga is not None:
            self.waga = Waga(self.waga).value
        if self.poziom_wcag not in (None, "A", "AA", "AAA"):
            raise ValueError(f"Nieprawidłowy poziom WCAG: {self.poziom_wcag!r}")
        for kryterium in self.kryteria_wcag:
            if not _KRYTERIUM_RE.match(kryterium):
                raise ValueError(f"Nieprawidłowe kryterium WCAG: {kryterium!r} (oczekiwano np. '1.4.3')")
        if self.poziom_pewnosci is not None and not 0.0 <= self.poziom_pewnosci <= 1.0:
            raise ValueError(f"Poziom pewności musi być w zakresie 0–1, jest {self.poziom_pewnosci}")
        if len(self.fragment_html) > MAX_FRAGMENT_HTML:
            self.fragment_html = self.fragment_html[: MAX_FRAGMENT_HTML - 1] + "…"
        if not self.id:
            self.id = identyfikator_problemu(self.url_podstrony, self.zrodlo, self.regula, self.selektor)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, dane: dict[str, Any]) -> "Problem":
        return cls(**dane)


@dataclass
class WynikStrony:
    """Wynik audytu jednej podstrony – zawartość pliku wynik.json."""

    url: str                            # final_url (po przekierowaniach)
    requested_url: str
    sprawdzono: str                     # czas audytu, ISO 8601 UTC
    problemy: list[Problem] = field(default_factory=list)
    narzedzia: dict[str, str] = field(default_factory=dict)   # np. {"axe-core": "4.12.1", "audytor": "0.1.0"}
    migawka: str | None = None          # nazwa folderu migawki (dom.html, zrzut, meta.json)
    http_status: int | None = None
    ostrzezenia: list[str] = field(default_factory=list)

    def podsumowanie(self) -> dict[str, Any]:
        """Liczby problemów wg statusu, wagi i źródła (do raportu i szybkiego podglądu)."""
        wg_statusu = {s.value: 0 for s in Status}
        wg_wagi = {w.value: 0 for w in KOLEJNOSC_WAG}
        wg_zrodla = {z.value: 0 for z in Zrodlo}
        for problem in self.problemy:
            wg_statusu[problem.status] += 1
            wg_zrodla[problem.zrodlo] += 1
            if problem.waga is not None and problem.status != Status.ODRZUCONY:
                wg_wagi[problem.waga] += 1
        return {
            "liczba_problemow": len(self.problemy),
            "wg_statusu": wg_statusu,
            "wg_wagi": wg_wagi,
            "wg_zrodla": wg_zrodla,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "url": self.url,
            "requested_url": self.requested_url,
            "http_status": self.http_status,
            "sprawdzono": self.sprawdzono,
            "narzedzia": self.narzedzia,
            "migawka": self.migawka,
            "podsumowanie": self.podsumowanie(),
            "ostrzezenia": self.ostrzezenia,
            "problemy": [p.to_dict() for p in self.problemy],
        }

    @classmethod
    def from_dict(cls, dane: dict[str, Any]) -> "WynikStrony":
        wersja = dane.get("schema_version")
        if wersja is None or wersja.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
            raise ValueError(f"Nieobsługiwana wersja formatu wyniku: {wersja!r} (obsługiwana {SCHEMA_VERSION})")
        return cls(
            url=dane["url"],
            requested_url=dane["requested_url"],
            sprawdzono=dane["sprawdzono"],
            problemy=[Problem.from_dict(p) for p in dane.get("problemy", [])],
            narzedzia=dane.get("narzedzia", {}),
            migawka=dane.get("migawka"),
            http_status=dane.get("http_status"),
            ostrzezenia=dane.get("ostrzezenia", []),
        )


def zapisz_wynik(wynik: WynikStrony, folder: str | Path) -> Path:
    """Zapisuje wynik do `<folder>/wynik.json` (UTF-8, czytelne wcięcia). Zwraca ścieżkę pliku."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    sciezka = folder / WYNIK_FILE
    sciezka.write_text(json.dumps(wynik.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return sciezka


def wczytaj_wynik(sciezka: str | Path) -> WynikStrony:
    """Wczytuje wynik.json – przyjmuje ścieżkę pliku albo folderu, w którym leży."""
    sciezka = Path(sciezka)
    if sciezka.is_dir():
        sciezka = sciezka / WYNIK_FILE
    return WynikStrony.from_dict(json.loads(sciezka.read_text(encoding="utf-8")))
