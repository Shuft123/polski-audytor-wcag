"""Zapis wyników (format z kontraktu, sekcja 2) do bazy i odczyt z powrotem.

    sesje = otworz_baze("sqlite:///audytor.db")      # albo postgresql+psycopg://...
    with sesje() as sesja:
        skan = zapisz_skan(sesja, [wynik_strony], url_startowy="https://pb.edu.pl/")
        sesja.commit()
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from audytor.wyniki import Problem as ProblemWynik
from audytor.wyniki import WynikStrony

from .models import Base, Podstrona, Problem, Skan, StatusSkanu


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
    )
