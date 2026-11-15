"""Zadania workera: wykonanie skanu zleconego przez API.

Przebieg (sprint 1 – jedna strona, `url_startowy` skanu):
    oczekuje -> w_trakcie -> skanuj_strone (render + axe-core) -> zapis podstrony -> zakonczony
                                         \\-> wyjątek ------------------------------> blad (opis_bledu)

Migawka i wynik.json lądują w `AUDYTOR_WYNIKI_DIR/skan-<id>/<strona>/`, wyniki także w bazie.
Pełny crawling wielu podstron (F1) i właściwa kolejka (F4) – sprint 3.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy.orm import Session, sessionmaker

from audytor.crawler.render import Renderer, RenderOptions, RobotsDisallowedError
from audytor.db import Skan, StatusSkanu, otworz_baze, zapisz_podstrone
from audytor.skan import skanuj_strone
from audytor.ustawienia import Ustawienia

from .celery_app import ZADANIE_SKANU, app

log = logging.getLogger(__name__)

MAX_OPIS_BLEDU = 2000


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


def wykonaj_skan(
    sesje: sessionmaker[Session],
    skan_id: int,
    ustawienia: Ustawienia,
    renderer: Callable[[Ustawienia], AbstractContextManager[Renderer]] = domyslny_renderer,
) -> StatusSkanu | None:
    """Wykonuje skan o podanym id i zapisuje wynik w bazie. Zwraca końcowy status (None = brak skanu)."""
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
        url = skan.url_startowy

    folder_skanu = ustawienia.wyniki_dir / f"skan-{skan_id}"
    try:
        with renderer(ustawienia) as r:
            wynik, _ = skanuj_strone(r, url, folder_skanu)
    except BaseException as exc:  # także SoftTimeLimitExceeded i KeyboardInterrupt – skan nie może utknąć
        log.exception("Skan #%s (%s) zakończony błędem", skan_id, url)
        with sesje() as sesja:
            skan = sesja.get(Skan, skan_id)
            skan.status = StatusSkanu.BLAD
            skan.opis_bledu = _opis_wyjatku(exc)
            skan.zakonczono = _teraz()
            sesja.commit()
        if not isinstance(exc, Exception):
            raise
        return StatusSkanu.BLAD

    with sesje() as sesja:
        skan = sesja.get(Skan, skan_id)
        zapisz_podstrone(sesja, skan, wynik)
        skan.status = StatusSkanu.ZAKONCZONY
        skan.zakonczono = _teraz()
        sesja.commit()
    log.info("Skan #%s (%s) zakończony: %d problemów", skan_id, url, len(wynik.problemy))
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
