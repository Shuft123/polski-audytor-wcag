"""API, sprint 2: parametry skanu (podstrony, limit, kroki), podstrony, fokus, deklaracja, zrzuty."""

import json
from contextlib import nullcontext
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from audytor.api import create_app
from audytor.axe import axe_na_problemy
from audytor.worker.kroki import NAZWY_KROKOW, KontekstPodstrony, KrokPodstrony, Kroki, KrokSkanu, domyslne_kroki
from audytor.worker.zadania import wykonaj_skan
from audytor.wyniki import WynikStrony

AXE = Path(__file__).parent.parent / "axe" / "data" / "axe_wynik_przyklad.json"
START = "https://gmina-testowa.pl/"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


@pytest.fixture
def kolejka():
    wyslane = []
    return wyslane


@pytest.fixture
def klient(ustawienia, sesje, kolejka):
    app = create_app(ustawienia, sesje=sesje, kolejka=kolejka.append, sprawdz_kolejke=lambda: True)
    with TestClient(app) as klient:
        yield klient


@pytest.fixture
def skaner(monkeypatch, sesje, ustawienia):
    """Wykonuje skan „bez przeglądarki”: podmieniony skanuj_strone zapisuje migawkę ze zrzutem (JPEG)."""
    from audytor.worker import zadania

    def skanuj(renderer, url, out_dir, name=None):
        nazwa = url.rstrip("/").rsplit("/", 1)[-1].replace(".", "-")
        folder = Path(out_dir) / nazwa
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "screenshot.jpg").write_bytes(JPEG)
        problemy = axe_na_problemy(json.loads(AXE.read_text(encoding="utf-8")), url)
        wynik = WynikStrony(url=url, requested_url=url, sprawdzono="2026-11-28T12:00:00+00:00", problemy=problemy,
                            migawka=nazwa, http_status=200)
        return wynik, folder

    def fokus(ctx: KontekstPodstrony):
        (ctx.folder / "mapa-fokusu.png").write_bytes(PNG)
        ctx.fokus = {"url": ctx.url, "sprawdzono": "2026-11-28T12:00:01+00:00", "zakonczenie": "koniec strony",
                     "podsumowanie": {"kroki": 3, "ok": 3}, "kroki": [], "ostrzezenia": [], "problemy": []}
        ctx.fokus_limit_krokow = 40
        ctx.fokus_mapa = "mapa-fokusu.png"

    def deklaracja(ctx):
        ctx.deklaracja = {"found": True, "declaration_url": START + "deklaracja", "method": "link", "status": "ok",
                          "confidence": 0.9, "verified": True}

    monkeypatch.setattr(zadania, "skanuj_strone", skanuj)
    kroki = Kroki(podstrony=(KrokPodstrony("fokus", fokus, tylko_startowa=True),),
                  skanu=(KrokSkanu("deklaracja", deklaracja),))
    return lambda skan_id: wykonaj_skan(sesje, skan_id, ustawienia, renderer=lambda _u: nullcontext(None),
                                        spij=lambda _s: None, kroki=kroki)


def test_api_step_names_match_worker_steps():
    domyslne = domyslne_kroki()
    assert set(NAZWY_KROKOW) == {k.nazwa for k in [*domyslne.podstrony, *domyslne.skanu]}


def test_create_scan_with_subpages_and_limits(klient, kolejka):
    odp = klient.post("/skany", json={
        "url": "https://gmina-testowa.pl",
        "podstrony": ["https://gmina-testowa.pl/kontakt", "https://inna-gmina.pl/", "https://gmina-testowa.pl/a#x"],
        "max_podstron": 2,
        "pomin_kroki": ["fokus", "fokus"],
        "parametry": {"podstrony": ["ignorowane"], "notatka": "test"},
    })

    assert odp.status_code == 202, odp.text
    skan = odp.json()
    assert skan["parametry"] == {
        "notatka": "test", "max_podstron": 2, "pomin_kroki": ["fokus"],
        "podstrony": [START + "kontakt", "https://inna-gmina.pl/", START + "a"],
    }
    assert skan["planowane_podstrony"] == 2                 # start + kontakt, limit 2
    assert any("inna witryna" in u for u in skan["uwagi"]) and any("ponad limit" in u for u in skan["uwagi"])
    assert kolejka == [skan["id"]]


@pytest.mark.parametrize(("pole", "wartosc"), [
    ("podstrony", ["kontakt.html"]),
    ("podstrony", ["ftp://gmina-testowa.pl/plik"]),
    ("max_podstron", 0),
    ("max_podstron", 51),
    ("pomin_kroki", ["axe"]),
])
def test_create_scan_rejects_invalid_options(klient, kolejka, pole, wartosc):
    odp = klient.post("/skany", json={"url": START, pole: wartosc})
    assert odp.status_code == 422
    assert kolejka == []


def test_subpages_results_focus_declaration_and_screenshots(klient, skaner):
    skan_id = klient.post("/skany", json={"url": START, "podstrony": [START + "kontakt"]}).json()["id"]
    skaner(skan_id)

    skan = klient.get(f"/skany/{skan_id}").json()
    assert skan["status"] == "zakonczony"
    assert (skan["planowane_podstrony"], skan["liczba_podstron"], skan["podstrony_z_bledem"]) == (2, 2, 0)

    podstrony = klient.get(f"/skany/{skan_id}/podstrony").json()
    assert [p["url"] for p in podstrony] == [START, START + "kontakt"]
    start, kontakt = podstrony
    assert start["test_fokusu"] and not kontakt["test_fokusu"]
    assert start["zrzut"] == f"/skany/{skan_id}/podstrony/{start['id']}/zrzut"
    assert start["mapa_fokusu"] == f"/skany/{skan_id}/podstrony/{start['id']}/mapa-fokusu"
    assert kontakt["mapa_fokusu"] is None

    zrzut = klient.get(start["zrzut"])
    assert zrzut.status_code == 200 and zrzut.headers["content-type"] == "image/jpeg" and zrzut.content == JPEG
    mapa = klient.get(start["mapa_fokusu"])
    assert mapa.status_code == 200 and mapa.headers["content-type"] == "image/png"
    assert klient.get(f"/skany/{skan_id}/podstrony/{kontakt['id']}/mapa-fokusu").status_code == 404

    wyniki = klient.get(f"/skany/{skan_id}/wyniki").json()
    assert wyniki["deklaracja"]["znaleziono"] and wyniki["deklaracja"]["url_deklaracji"] == START + "deklaracja"
    w_start, w_kontakt = wyniki["podstrony"]
    assert w_start["fokus"]["limit_krokow"] == 40 and w_kontakt["fokus"] is None
    assert w_start["id"] == start["id"] and w_start["zrzut"] == start["zrzut"]
    assert len(w_start["problemy"]) == 6                     # format wynik.json bez zmian


def test_results_before_scan_runs(klient):
    skan_id = klient.post("/skany", json={"url": START}).json()["id"]
    wyniki = klient.get(f"/skany/{skan_id}/wyniki").json()
    assert wyniki["podstrony"] == [] and wyniki["deklaracja"] is None
    assert klient.get(f"/skany/{skan_id}/podstrony").json() == []


def test_screenshot_of_other_scan_or_missing_is_404(klient, skaner):
    a = klient.post("/skany", json={"url": START}).json()["id"]
    b = klient.post("/skany", json={"url": START}).json()["id"]
    skaner(a)
    podstrona_a = klient.get(f"/skany/{a}/podstrony").json()[0]["id"]

    assert klient.get(f"/skany/{b}/podstrony/{podstrona_a}/zrzut").status_code == 404   # podstrona innego skanu
    assert klient.get(f"/skany/{a}/podstrony/9999/zrzut").status_code == 404
    assert klient.get("/skany/9999/podstrony").status_code == 404


def test_screenshot_path_cannot_escape_results_folder(klient, skaner, sesje, ustawienia):
    from audytor.db import Podstrona

    skan_id = klient.post("/skany", json={"url": START}).json()["id"]
    skaner(skan_id)
    (ustawienia.wyniki_dir / "screenshot.jpg").write_bytes(JPEG)          # plik poza folderem skanu
    with sesje() as sesja:
        podstrona = sesja.query(Podstrona).filter_by(skan_id=skan_id).one()
        podstrona.migawka = ".."
        sesja.commit()
        pid = podstrona.id

    assert klient.get(f"/skany/{skan_id}/podstrony/{pid}/zrzut").status_code == 404
