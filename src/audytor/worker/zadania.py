"""Zadania workera: wykonanie skanu zleconego przez API.

Przebieg (sprint 2 – lista podstron, F6):
    oczekuje -> w_trakcie -> dla każdej podstrony: skanuj_strone (render + axe-core) -> zapis podstrony
                          -> zakonczony (gdy choć jedna podstrona sprawdzona) albo blad (gdy żadna)

Lista podstron: `url_startowy` + `parametry["podstrony"]` (tylko ta sama witryna, limit `max_podstron`) –
`audytor.skan.lista_podstron`. Jedna przeglądarka na cały skan; między podstronami tej samej witryny
pauza `AUDYTOR_OPOZNIENIE_S` albo Crawl-delay z robots.txt. Podstrona, której nie udało się sprawdzić
(robots.txt, timeout), jest zapisywana z polem `blad` – skan idzie dalej. Każda podstrona trafia do bazy
od razu, więc API pokazuje postęp w trakcie skanu.

Migawki i wynik.json lądują w `AUDYTOR_WYNIKI_DIR/skan-<id>/<podstrona>/`, wyniki także w bazie.
Pełna kolejka z ponawianiem (F4) – sprint 3.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy.orm import Session, sessionmaker

from audytor.crawler.render import Renderer, RenderOptions, RobotsDisallowedError
from audytor.db import Skan, StatusSkanu, otworz_baze, zapisz_podstrone
from audytor.skan import Ogranicznik, lista_podstron, skanuj_strone
from audytor.skan.lista import crawl_delay_z_renderera
from audytor.ustawienia import Ustawienia
from audytor.wyniki import WynikStrony, teraz_utc

from .celery_app import ZADANIE_SKANU, app

log = logging.getLogger(__name__)

MAX_OPIS_BLEDU = 2000
# Ile sekund skanu na nowe podstrony: zapas przed miękkim limitem Celery (task_soft_time_limit = 540 s),
# żeby skan długiej listy skończył się porządnie (reszta podstron z „blad”), a nie wyjątkiem w połowie.
BUDZET_S = 480


def _teraz() -> datetime:
    return datetime.now(timezone.utc)


def domyslny_renderer(ustawienia: Ustawienia) -> Renderer:
    options = RenderOptions(
        timeout_ms=int(ustawienia.timeout_s * 1000),
        screenshot_type="jpeg",
        save_mhtml=False,
        channel=ustawienia.przegladarka,
    )
    return Renderer(options)


def _opis_wyjatku(exc: BaseException) -> str:
    if isinstance(exc, RobotsDisallowedError):
        return f"Pominięto zgodnie z robots.txt – {exc}"
    tekst = str(exc).strip() or type(exc).__name__
    return tekst[:MAX_OPIS_BLEDU]


def _nieudana(url: str, opis: str) -> WynikStrony:
    return WynikStrony(url=url, requested_url=url, sprawdzono=teraz_utc(), blad=opis)


def _oznacz_blad(sesje: sessionmaker[Session], skan_id: int, opis: str) -> None:
    with sesje() as sesja:
        skan = sesja.get(Skan, skan_id)
        skan.status = StatusSkanu.BLAD
        skan.opis_bledu = opis[:MAX_OPIS_BLEDU]
        skan.zakonczono = _teraz()
        sesja.commit()


def wykonaj_skan(
    sesje: sessionmaker[Session],
    skan_id: int,
    ustawienia: Ustawienia,
    renderer: Callable[[Ustawienia], AbstractContextManager[Renderer]] = domyslny_renderer,
    budzet_s: float = BUDZET_S,
    spij: Callable[[float], None] = time.sleep,
) -> StatusSkanu | None:
    """Wykonuje skan o podanym id (wszystkie jego podstrony) i zapisuje wyniki w bazie.

    Zwraca końcowy status (None = brak skanu).
    """
    with sesje() as sesja:
        skan = sesja.get(Skan, skan_id)
        if skan is None:
            log.warning("Skan #%s nie istnieje – pomijam", skan_id)
            return None
        if skan.status != StatusSkanu.OCZEKUJE:
            # Np. to samo zadanie dostarczone drugi raz po restarcie workera.
            log.info("Skan #%s ma status %s – pomijam", skan_id, skan.status)
            return skan.status
        skan.status = StatusSkanu.W_TRAKCIE
        skan.rozpoczeto = _teraz()
        sesja.commit()
        lista = lista_podstron(skan.url_startowy, skan.parametry)

    for uwaga in lista.pominiete:
        log.info("Skan #%s: %s", skan_id, uwaga)
    folder_skanu = ustawienia.wyniki_dir / f"skan-{skan_id}"
    start = time.monotonic()
    zapisane: set[str] = set()       # final_url zapisanych podstron (dwa adresy mogą przekierować w to samo miejsce)
    udane = 0
    pierwszy_blad: str | None = None

    try:
        with renderer(ustawienia) as r:
            ogranicznik = Ogranicznik(ustawienia.opoznienie_s, crawl_delay_z_renderera(r), spij=spij)
            for url in lista.adresy:
                if time.monotonic() - start > budzet_s:
                    wynik = _nieudana(url, f"Nie sprawdzono – przekroczony czas skanu ({budzet_s:.0f} s)")
                else:
                    ogranicznik.czekaj(url)
                    try:
                        wynik, _ = skanuj_strone(r, url, folder_skanu)
                    except Exception as exc:   # jedna zepsuta podstrona nie przerywa skanu
                        log.warning("Skan #%s: podstrona %s nie sprawdzona: %s", skan_id, url, exc)
                        wynik = _nieudana(url, _opis_wyjatku(exc))
                    finally:
                        ogranicznik.odwiedzono(url)

                if wynik.url in zapisane:
                    log.info("Skan #%s: %s to ta sama strona co już sprawdzona (%s)", skan_id, url, wynik.url)
                    continue
                zapisane.add(wynik.url)
                if wynik.blad is None:
                    udane += 1
                elif pierwszy_blad is None:
                    pierwszy_blad = wynik.blad
                with sesje() as sesja:
                    zapisz_podstrone(sesja, sesja.get(Skan, skan_id), wynik)
                    sesja.commit()
    except BaseException as exc:  # przeglądarka nie wstała, SoftTimeLimitExceeded, KeyboardInterrupt…
        log.exception("Skan #%s zakończony błędem", skan_id)
        _oznacz_blad(sesje, skan_id, _opis_wyjatku(exc))
        if not isinstance(exc, Exception):
            raise
        return StatusSkanu.BLAD

    if udane == 0:
        _oznacz_blad(sesje, skan_id, pierwszy_blad or "Nie sprawdzono żadnej podstrony")
        return StatusSkanu.BLAD
    with sesje() as sesja:
        skan = sesja.get(Skan, skan_id)
        skan.status = StatusSkanu.ZAKONCZONY
        skan.zakonczono = _teraz()
        sesja.commit()
    log.info("Skan #%s zakończony: %d z %d podstron sprawdzonych", skan_id, udane, len(zapisane))
    return StatusSkanu.ZAKONCZONY


@lru_cache(maxsize=4)
def _sesje(db_url: str) -> sessionmaker[Session]:
    # Jedna pula połączeń na proces workera. Tabele tworzą migracje (alembic upgrade head).
    return otworz_baze(db_url, utworz=False)


@app.task(name=ZADANIE_SKANU)
def skanuj_strone_zadanie(skan_id: int) -> str | None:
    ustawienia = Ustawienia.ze_srodowiska()
    status = wykonaj_skan(_sesje(ustawienia.db_url), skan_id, ustawienia)
    return status.value if status else None
