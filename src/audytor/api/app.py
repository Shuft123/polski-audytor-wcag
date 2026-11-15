"""Szkielet REST API (F21, sprint 1): zdrowie usługi, zlecenie skanu, status i wyniki.

Uruchomienie:
    audytor-api                       # = uvicorn audytor.api.app:create_app --factory
Dokumentacja interaktywna (Swagger): http://localhost:8000/docs
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from audytor import __version__
from audytor.db import Skan, StatusSkanu, otworz_baze, wynik_podstrony
from audytor.ustawienia import Ustawienia

from .schematy import NowySkan, SkanOut, WynikiSkanu, Zdrowie

log = logging.getLogger(__name__)

Kolejka = Callable[[int], None]            # wysyła skan o danym id do workera
SprawdzKolejke = Callable[[], bool]        # True, gdy broker (Redis) odpowiada


def _sesja(request: Request) -> Iterator[Session]:
    with request.app.state.sesje() as s:
        yield s


# Na poziomie modułu (nie w create_app), bo FastAPI rozwiązuje adnotacje przy `from __future__ import annotations`.
SesjaDep = Annotated[Session, Depends(_sesja)]


def _pobierz_skan(s: Session, skan_id: int) -> Skan:
    skan = s.get(Skan, skan_id)
    if skan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Nie ma skanu #{skan_id}")
    return skan


def _kolejka_celery(ustawienia: Ustawienia) -> tuple[Kolejka, SprawdzKolejke]:
    import redis

    from audytor.worker.celery_app import ZADANIE_SKANU, utworz_celery

    celery = utworz_celery(ustawienia)

    def wyslij(skan_id: int) -> None:
        celery.send_task(ZADANIE_SKANU, args=[skan_id])

    def sprawdz() -> bool:
        try:
            return bool(redis.Redis.from_url(ustawienia.redis_url, socket_connect_timeout=1, socket_timeout=1).ping())
        except redis.RedisError:
            return False

    return wyslij, sprawdz


def create_app(
    ustawienia: Ustawienia | None = None,
    sesje: sessionmaker[Session] | None = None,
    kolejka: Kolejka | None = None,
    sprawdz_kolejke: SprawdzKolejke | None = None,
) -> FastAPI:
    """Tworzy aplikację. Parametry pozwalają w testach podmienić bazę i kolejkę."""
    ustawienia = ustawienia or Ustawienia.ze_srodowiska()
    if sesje is None:
        sesje = otworz_baze(ustawienia.db_url, utworz=False)   # tabele tworzy: alembic upgrade head
    if kolejka is None or sprawdz_kolejke is None:
        domyslna, domyslne_sprawdzenie = _kolejka_celery(ustawienia)
        kolejka = kolejka or domyslna
        sprawdz_kolejke = sprawdz_kolejke or domyslne_sprawdzenie

    app = FastAPI(
        title="Polski audytor WCAG – API",
        version=__version__,
        description="Zlecanie skanów dostępności (WCAG 2.1 AA) i pobieranie wyników.",
    )
    app.state.sesje = sesje
    app.state.kolejka = kolejka
    app.state.sprawdz_kolejke = sprawdz_kolejke

    @app.get("/health", response_model=Zdrowie, tags=["usługa"],
             responses={503: {"model": Zdrowie, "description": "Baza lub kolejka niedostępna"}})
    def health(request: Request, s: SesjaDep):
        """Stan usługi: API, baza danych (z tabelami) i broker kolejki."""
        try:
            s.execute(text("SELECT 1 FROM skan LIMIT 1"))
            baza = "ok"
        except (ProgrammingError, OperationalError) as exc:
            komunikat = str(exc.orig).lower()
            brak_tabeli = "no such table" in komunikat or "does not exist" in komunikat
            baza = "brak tabel – uruchom: alembic upgrade head" if brak_tabeli else "niedostepna"
        except DBAPIError:
            baza = "niedostepna"
        kolejka_ok = request.app.state.sprawdz_kolejke()
        wynik = Zdrowie(
            status="ok" if baza == "ok" and kolejka_ok else "blad",
            wersja=__version__,
            baza=baza,
            kolejka="ok" if kolejka_ok else "niedostepna",
        )
        kod = status.HTTP_200_OK if wynik.status == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(wynik.model_dump(), status_code=kod)

    @app.post("/skany", response_model=SkanOut, status_code=status.HTTP_202_ACCEPTED, tags=["skany"],
              responses={503: {"description": "Nie udało się dodać skanu do kolejki"}})
    def utworz_skan(dane: NowySkan, request: Request, response: Response, s: SesjaDep):
        """Zleca skan strony. Skan trafia do kolejki ze statusem `oczekuje`; stan sprawdzaj przez GET."""
        skan = Skan(
            url_startowy=dane.url,
            status=StatusSkanu.OCZEKUJE,
            utworzono=datetime.now(timezone.utc),
            parametry=dane.parametry,
        )
        s.add(skan)
        s.commit()
        try:
            request.app.state.kolejka(skan.id)
        except Exception as exc:
            log.exception("Nie udało się wysłać skanu #%s do kolejki", skan.id)
            skan.status = StatusSkanu.BLAD
            skan.opis_bledu = f"Nie udało się dodać skanu do kolejki: {exc}"[:2000]
            skan.zakonczono = datetime.now(timezone.utc)
            s.commit()
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                f"Kolejka skanów niedostępna (skan #{skan.id} oznaczony jako błąd)") from exc
        response.headers["Location"] = f"/skany/{skan.id}"
        return SkanOut.z_bazy(skan)

    @app.get("/skany", response_model=list[SkanOut], tags=["skany"])
    def lista_skanow(s: SesjaDep, limit: Annotated[int, Query(ge=1, le=200)] = 20):
        """Ostatnie skany, od najnowszego."""
        skany = s.scalars(select(Skan).order_by(Skan.id.desc()).limit(limit)).all()
        return [SkanOut.z_bazy(skan) for skan in skany]

    @app.get("/skany/{skan_id}", response_model=SkanOut, tags=["skany"],
             responses={404: {"description": "Nie ma takiego skanu"}})
    def odczytaj_skan(skan_id: int, s: SesjaDep):
        """Status skanu: `oczekuje` → `w_trakcie` → `zakonczony` albo `blad` (wtedy `opis_bledu`)."""
        return SkanOut.z_bazy(_pobierz_skan(s, skan_id))

    @app.get("/skany/{skan_id}/wyniki", response_model=WynikiSkanu, tags=["skany"],
             responses={404: {"description": "Nie ma takiego skanu"}})
    def wyniki_skanu(skan_id: int, s: SesjaDep):
        """Wyniki skanu w formacie wynik.json (jeden element na podstronę). Pusta lista, dopóki skan trwa."""
        skan = _pobierz_skan(s, skan_id)
        return WynikiSkanu(
            skan=SkanOut.z_bazy(skan),
            podstrony=[wynik_podstrony(p).to_dict() for p in skan.podstrony],
        )

    return app
