"""Zapis wyników (format z kontraktu, sekcja 2) do bazy i odczyt z powrotem.

    sesje = otworz_baze("sqlite:///audytor.db")      # albo postgresql+psycopg://...
    with sesje() as sesja:
        skan = zapisz_skan(sesja, [wynik_strony], url_startowy="https://pb.edu.pl/")
        sesja.commit()
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from audytor.wyniki import Problem as ProblemWynik
from audytor.wyniki import WynikStrony

from .models import Base, Podstrona, Problem, Skan, StatusSkanu, WynikDeklaracji, WynikFokusu


def _czas(iso: str) -> datetime:
    czas = datetime.fromisoformat(iso)
    return czas if czas.tzinfo else czas.replace(tzinfo=timezone.utc)


def _iso(czas: datetime) -> str:
    # SQLite nie przechowuje strefy czasowej – zapisujemy UTC, więc brak strefy = UTC.
    if czas.tzinfo is None:
        czas = czas.replace(tzinfo=timezone.utc)
    return czas.astimezone(timezone.utc).isoformat(timespec="seconds")


def utworz_tabele(engine: Engine) -> None:
    """Tworzy brakujące tabele. Tymczasowo, do czasu migracji Alembic (osoba 6)."""
    Base.metadata.create_all(engine)


def otworz_baze(url: str, utworz: bool = True) -> sessionmaker[Session]:
    """Łączy się z bazą (URL w formacie SQLAlchemy) i zwraca fabrykę sesji."""
    engine = create_engine(url)
    if engine.dialect.name == "sqlite":
        plik = engine.url.database
        if plik and plik != ":memory:" and not plik.startswith("file:"):
            Path(plik).parent.mkdir(parents=True, exist_ok=True)

        # SQLite domyślnie ignoruje klucze obce (a więc i ON DELETE CASCADE).
        @event.listens_for(engine, "connect")
        def _wlacz_klucze_obce(polaczenie, _):
            polaczenie.execute("PRAGMA foreign_keys=ON")

    if utworz:
        utworz_tabele(engine)
    return sessionmaker(engine, expire_on_commit=False)


def problem_do_bazy(problem: ProblemWynik) -> Problem:
    return Problem(
        klucz=problem.id,
        zrodlo=problem.zrodlo,
        regula=problem.regula,
        kryteria_wcag=list(problem.kryteria_wcag),
        poziom_wcag=problem.poziom_wcag,
        status=problem.status,
        waga=problem.waga,
        selektor=problem.selektor,
        fragment_html=problem.fragment_html,
        opis=problem.opis,
        szczegoly=problem.szczegoly,
        link_pomocy=problem.link_pomocy,
        poziom_pewnosci=problem.poziom_pewnosci,
        uzasadnienie=problem.uzasadnienie,
        wykryto=_czas(problem.wykryto),
    )


def problem_z_bazy(problem: Problem, url_podstrony: str) -> ProblemWynik:
    return ProblemWynik(
        id=problem.klucz,
        url_podstrony=url_podstrony,
        zrodlo=problem.zrodlo,
        regula=problem.regula,
        kryteria_wcag=list(problem.kryteria_wcag),
        poziom_wcag=problem.poziom_wcag,
        status=problem.status,
        waga=problem.waga,
        selektor=problem.selektor,
        fragment_html=problem.fragment_html,
        opis=problem.opis,
        szczegoly=problem.szczegoly,
        link_pomocy=problem.link_pomocy,
        poziom_pewnosci=problem.poziom_pewnosci,
        uzasadnienie=problem.uzasadnienie,
        wykryto=_iso(problem.wykryto),
    )


def zapisz_podstrone(sesja: Session, skan: Skan, wynik: WynikStrony) -> Podstrona:
    """Dodaje do skanu podstronę z jej problemami (bez commit – o tym decyduje wywołujący)."""
    podstrona = Podstrona(
        url=wynik.url,
        requested_url=wynik.requested_url,
        http_status=wynik.http_status,
        sprawdzono=_czas(wynik.sprawdzono),
        migawka=wynik.migawka,
        narzedzia=dict(wynik.narzedzia),
        ostrzezenia=list(wynik.ostrzezenia),
        blad=wynik.blad,
        problemy=[problem_do_bazy(p) for p in wynik.problemy],
    )
    skan.podstrony.append(podstrona)
    sesja.flush()
    return podstrona


def zapisz_skan(
    sesja: Session,
    wyniki: Iterable[WynikStrony],
    url_startowy: str,
    parametry: dict | None = None,
) -> Skan:
    """Zapisuje zakończony skan (np. z wiersza poleceń) razem z podstronami i problemami."""
    wyniki = list(wyniki)
    czasy = [_czas(w.sprawdzono) for w in wyniki]
    teraz = datetime.now(timezone.utc)
    skan = Skan(
        url_startowy=url_startowy,
        status=StatusSkanu.ZAKONCZONY,
        utworzono=min(czasy, default=teraz),
        rozpoczeto=min(czasy, default=teraz),
        zakonczono=teraz,
        parametry=dict(parametry or {}),
    )
    sesja.add(skan)
    for wynik in wyniki:
        zapisz_podstrone(sesja, skan, wynik)
    return skan


def wynik_podstrony(podstrona: Podstrona) -> WynikStrony:
    """Odtwarza `WynikStrony` (format wynik.json) z rekordu w bazie – np. dla API albo raportu PDF."""
    return WynikStrony(
        url=podstrona.url,
        requested_url=podstrona.requested_url,
        sprawdzono=_iso(podstrona.sprawdzono),
        problemy=[problem_z_bazy(p, podstrona.url) for p in podstrona.problemy],
        narzedzia=dict(podstrona.narzedzia),
        migawka=podstrona.migawka,
        http_status=podstrona.http_status,
        ostrzezenia=list(podstrona.ostrzezenia),
        blad=podstrona.blad,
    )


# --- wyniki testu fokusu i deklaracji (migracja 0002) -------------------------------------------------
# Funkcje przyjmują słowniki z `to_dict()` modułów fokus i deklaracja, a nie ich klasy: dzięki temu baza
# nie importuje Playwrighta ani Pillow, a moduły mogą rozwijać swoje klasy niezależnie.

def zapisz_wynik_fokusu(
    sesja: Session,
    podstrona: Podstrona,
    wynik: dict[str, Any],
    limit_krokow: int | None = None,
    mapa: str | None = None,
) -> WynikFokusu:
    """Zapisuje wynik testu fokusu (`WynikFokusu.to_dict()`) przy podstronie.

    Problemy z wyniku (`wynik["problemy"]`, format wspólny – kontrakt, sekcja 2) są dopisywane do tabeli
    `problem` tej podstrony; problem o tym samym `id` co już zapisany jest pomijany.
    Ponowne wywołanie dla tej samej podstrony zastępuje poprzedni wynik fokusu.
    """
    # Aktualizacja istniejącego rekordu zamiast podmiany: przy relacji 1:1 SQLAlchemy wstawiłby nowy
    # wiersz przed usunięciem starego i złamał ograniczenie UNIQUE(podstrona_id).
    rekord = podstrona.fokus or WynikFokusu()
    rekord.sprawdzono = _czas(wynik["sprawdzono"])
    rekord.zakonczenie = wynik.get("zakonczenie", "")
    rekord.limit_krokow = limit_krokow
    rekord.podsumowanie = dict(wynik.get("podsumowanie", {}))
    rekord.kroki = list(wynik.get("kroki", []))
    rekord.ostrzezenia = list(wynik.get("ostrzezenia", []))
    rekord.mapa = mapa
    podstrona.fokus = rekord
    _dopisz_problemy(podstrona, wynik.get("problemy", []))
    sesja.flush()
    return rekord


def zapisz_wynik_deklaracji(sesja: Session, skan: Skan, wynik: dict[str, Any],
                            sprawdzono: str | None = None) -> WynikDeklaracji:
    """Zapisuje wynik wyszukania deklaracji (`DeclarationResult.to_dict()`) przy skanie.

    `wynik["walidacja"]` (opcjonalnie) – wynik walidatora F18 v1. Ponowne wywołanie zastępuje poprzedni wynik.
    """
    rekord = skan.deklaracja or WynikDeklaracji()    # aktualizacja zamiast podmiany – jak w fokusie
    rekord.sprawdzono = _czas(sprawdzono) if sprawdzono else datetime.now(timezone.utc)
    rekord.znaleziono = bool(wynik["found"])
    rekord.url_deklaracji = wynik.get("declaration_url")
    rekord.metoda = wynik["method"]
    rekord.status = wynik["status"]
    rekord.pewnosc = float(wynik["confidence"])
    rekord.zweryfikowano = bool(wynik["verified"])
    rekord.identyfikatory_a11y = list(wynik.get("a11y_ids", []))
    rekord.brakujace_identyfikatory = list(wynik.get("missing_required_ids", []))
    rekord.kandydaci = list(wynik.get("candidates", []))
    rekord.ostrzezenia = list(wynik.get("warnings", []))
    rekord.walidacja = wynik.get("walidacja")
    skan.deklaracja = rekord
    sesja.flush()
    return rekord


def _dopisz_problemy(podstrona: Podstrona, problemy: Iterable[dict[str, Any]]) -> None:
    znane = {p.klucz for p in podstrona.problemy}
    for dane in problemy:
        problem = ProblemWynik.from_dict(dane)    # sprawdza zgodność z kontraktem (źródło, status, kryteria)
        if problem.id not in znane:
            znane.add(problem.id)
            podstrona.problemy.append(problem_do_bazy(problem))


def wynik_fokusu_dict(podstrona: Podstrona) -> dict[str, Any] | None:
    """Wynik testu fokusu podstrony w postaci dla API/raportu (None = test nie był uruchamiany)."""
    f = podstrona.fokus
    if f is None:
        return None
    return {
        "url": podstrona.url,
        "sprawdzono": _iso(f.sprawdzono),
        "zakonczenie": f.zakonczenie,
        "limit_krokow": f.limit_krokow,
        "podsumowanie": dict(f.podsumowanie),
        "ostrzezenia": list(f.ostrzezenia),
        "mapa": f.mapa,
        "kroki": list(f.kroki),
    }


def wynik_deklaracji_dict(skan: Skan) -> dict[str, Any] | None:
    """Wynik deklaracji skanu w postaci dla API/raportu (None = nie sprawdzano)."""
    d = skan.deklaracja
    if d is None:
        return None
    return {
        "sprawdzono": _iso(d.sprawdzono),
        "znaleziono": d.znaleziono,
        "url_deklaracji": d.url_deklaracji,
        "metoda": d.metoda,
        "status": d.status,
        "pewnosc": d.pewnosc,
        "zweryfikowano": d.zweryfikowano,
        "identyfikatory_a11y": list(d.identyfikatory_a11y),
        "brakujace_identyfikatory": list(d.brakujace_identyfikatory),
        "ostrzezenia": list(d.ostrzezenia),
        "walidacja": d.walidacja,
        "kandydaci": list(d.kandydaci),
    }
