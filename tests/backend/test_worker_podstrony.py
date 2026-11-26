"""Skan listy podstron w workerze (F6, sprint 2) – bez brokera Celery i bez przeglądarki."""

import json
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from audytor.axe import axe_na_problemy
from audytor.crawler.render import RenderError, RobotsDisallowedError
from audytor.db import Skan, StatusSkanu
from audytor.wyniki import WynikStrony

AXE = Path(__file__).parent.parent / "axe" / "data" / "axe_wynik_przyklad.json"
START = "https://gmina-testowa.pl/"


def _wynik(url: str) -> WynikStrony:
    problemy = axe_na_problemy(json.loads(AXE.read_text(encoding="utf-8")), url)
    return WynikStrony(url=url, requested_url=url, sprawdzono="2026-11-26T12:00:00+00:00", problemy=problemy,
                       narzedzia={"axe-core": "4.12.1"}, migawka="m", http_status=200)


@pytest.fixture
def strony(monkeypatch):
    """Podmienia skanuj_strone: wynik dla każdego adresu albo wyjątek z `bledy`, przekierowania z `przekierowania`."""
    from audytor.worker import zadania

    stan = {"wywolania": [], "bledy": {}, "przekierowania": {}}

    def skanuj(renderer, url, out_dir, name=None):
        stan["wywolania"].append(url)
        if url in stan["bledy"]:
            raise stan["bledy"][url]
        return _wynik(stan["przekierowania"].get(url, url)), Path(out_dir) / "x"

    monkeypatch.setattr(zadania, "skanuj_strone", skanuj)
    stan["renderer"] = lambda _ustawienia: nullcontext(None)
    return stan


def _skan(sesje, parametry) -> int:
    with sesje() as sesja:
        skan = Skan(url_startowy=START, status=StatusSkanu.OCZEKUJE, utworzono=datetime.now(timezone.utc),
                    parametry=parametry)
        sesja.add(skan)
        sesja.commit()
        return skan.id


def _wykonaj(sesje, ustawienia, strony, skan_id, **kw):
    from audytor.worker.zadania import wykonaj_skan

    pauzy = []
    status = wykonaj_skan(sesje, skan_id, ustawienia, renderer=strony["renderer"], spij=pauzy.append, **kw)
    return status, pauzy


def test_all_subpages_scanned_in_order_with_axe_results(sesje, ustawienia, strony):
    skan_id = _skan(sesje, {"podstrony": [START + "kontakt", START + "aktualnosci", START + "kontakt#mapa"]})
    status, _ = _wykonaj(sesje, ustawienia, strony, skan_id)

    assert status == StatusSkanu.ZAKONCZONY
    assert strony["wywolania"] == [START, START + "kontakt", START + "aktualnosci"]   # bez duplikatu z #
    with sesje() as sesja:
        skan = sesja.get(Skan, skan_id)
        assert [p.url for p in skan.podstrony] == strony["wywolania"]
        assert all(len(p.problemy) == 6 and p.blad is None for p in skan.podstrony)


def test_failed_subpage_does_not_stop_scan(sesje, ustawienia, strony):
    zablokowana = START + "prywatne"
    strony["bledy"] = {
        zablokowana: RobotsDisallowedError(zablokowana, SimpleNamespace(status="ok", robots_url=START + "robots.txt")),
        START + "wolna": RenderError("Przekroczono limit 30000 ms"),
    }
    skan_id = _skan(sesje, {"podstrony": [zablokowana, START + "wolna", START + "kontakt"]})
    status, _ = _wykonaj(sesje, ustawienia, strony, skan_id)

    assert status == StatusSkanu.ZAKONCZONY
    with sesje() as sesja:
        skan = sesja.get(Skan, skan_id)
        bledy = {p.url: p.blad for p in skan.podstrony}
        assert bledy[START] is None and bledy[START + "kontakt"] is None
        assert bledy[zablokowana].startswith("Pominięto zgodnie z robots.txt")
        assert "limit 30000 ms" in bledy[START + "wolna"]
        assert skan.opis_bledu is None


def test_scan_with_no_page_checked_is_error(sesje, ustawienia, strony):
    strony["bledy"] = {START: RenderError("Strona nie odpowiada")}
    skan_id = _skan(sesje, {})
    status, _ = _wykonaj(sesje, ustawienia, strony, skan_id)
    assert status == StatusSkanu.BLAD
    with sesje() as sesja:
        assert sesja.get(Skan, skan_id).opis_bledu == "Strona nie odpowiada"


def test_other_sites_and_limit_respected(sesje, ustawienia, strony):
    podstrony = ["https://inna-gmina.pl/", "https://bip.gmina-testowa.pl/"] + [f"{START}s{i}" for i in range(10)]
    skan_id = _skan(sesje, {"podstrony": podstrony, "max_podstron": 3})
    _wykonaj(sesje, ustawienia, strony, skan_id)
    assert strony["wywolania"] == [START, START + "s0", START + "s1"]


def test_redirect_to_already_scanned_page_saved_once(sesje, ustawienia, strony):
    strony["przekierowania"] = {START + "index.php": START}
    skan_id = _skan(sesje, {"podstrony": [START + "index.php", START + "kontakt"]})
    assert _wykonaj(sesje, ustawienia, strony, skan_id)[0] == StatusSkanu.ZAKONCZONY
    with sesje() as sesja:
        assert [p.url for p in sesja.get(Skan, skan_id).podstrony] == [START, START + "kontakt"]


def test_pause_between_pages_of_same_site(sesje, ustawienia, strony):
    from dataclasses import replace

    skan_id = _skan(sesje, {"podstrony": [START + "a", START + "b"]})
    _, pauzy = _wykonaj(sesje, replace(ustawienia, opoznienie_s=2.0), strony, skan_id)
    assert len(pauzy) == 2 and all(0 < p <= 2.0 for p in pauzy)     # przed 2. i 3. stroną, nie przed 1.


def test_time_budget_marks_remaining_pages(sesje, ustawienia, strony):
    skan_id = _skan(sesje, {"podstrony": [START + "a", START + "b"]})
    status, _ = _wykonaj(sesje, ustawienia, strony, skan_id, budzet_s=-1)
    assert status == StatusSkanu.BLAD                     # nic nie zdążyło się sprawdzić
    assert strony["wywolania"] == []
    with sesje() as sesja:
        assert all("przekroczony czas skanu" in p.blad for p in sesja.get(Skan, skan_id).podstrony)


def test_progress_visible_during_scan(sesje, ustawienia, strony):
    """Każda podstrona jest w bazie zaraz po sprawdzeniu – API pokazuje postęp, zanim skan się skończy."""
    from audytor.worker import zadania

    widoczne = []
    oryginal = zadania.skanuj_strone

    def skanuj_i_podejrzyj(renderer, url, out_dir, name=None):
        with sesje() as sesja:
            widoczne.append(len(sesja.get(Skan, skan_id).podstrony))
        return oryginal(renderer, url, out_dir, name)

    zadania.skanuj_strone = skanuj_i_podejrzyj
    try:
        skan_id = _skan(sesje, {"podstrony": [START + "a", START + "b"]})
        _wykonaj(sesje, ustawienia, strony, skan_id)
    finally:
        zadania.skanuj_strone = oryginal
    assert widoczne == [0, 1, 2]
