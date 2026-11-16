"""Cały przebieg przez API z prawdziwą przeglądarką: POST /skany -> worker (render + axe-core) -> wyniki.

Kolejka wykonuje zadanie od razu w tym samym procesie (bez Redisa). Strona z lokalnego serwera HTTP.
Pomijany, gdy Chromium nie jest zainstalowany. Inna przeglądarka: AUDYTOR_PRZEGLADARKA=chrome / msedge.
"""

import functools
import http.server
import os
import threading
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("playwright")

from audytor.api import create_app  # noqa: E402
from audytor.crawler.render import Renderer, RenderOptions  # noqa: E402
from audytor.worker.zadania import wykonaj_skan  # noqa: E402

pytestmark = pytest.mark.browser

STRONA = """<!doctype html>
<html><head><meta charset="utf-8"><title>Gmina testowa</title></head>
<body><h1>Gmina</h1><img src="herb.png"><a href="/aktualnosci"></a></body></html>
"""


class _CichyHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def strona(tmp_path_factory):
    root = tmp_path_factory.mktemp("strona-api")
    (root / "index.html").write_text(STRONA, encoding="utf-8")
    (root / "robots.txt").write_text("User-agent: *\nDisallow: /prywatne/\n", encoding="utf-8")
    serwer = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(_CichyHandler, directory=str(root)))
    threading.Thread(target=serwer.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{serwer.server_address[1]}"
    serwer.shutdown()


@pytest.fixture
def ustawienia_przegladarki(ustawienia):
    ust = replace(ustawienia, przegladarka=os.environ.get("AUDYTOR_PRZEGLADARKA") or None, timeout_s=15)
    try:
        with Renderer(RenderOptions(channel=ust.przegladarka)):
            pass
    except Exception as exc:
        pytest.skip(f"Przeglądarka niedostępna: {exc}")
    return ust


def _szybki_renderer(ust):
    return Renderer(RenderOptions(channel=ust.przegladarka, settle_ms=100, network_idle_ms=1000,
                                  cookie_wait_ms=300, save_mhtml=False, screenshot_type="jpeg"))


@pytest.fixture
def klient(ustawienia_przegladarki, sesje):
    def kolejka_natychmiastowa(skan_id):
        wykonaj_skan(sesje, skan_id, ustawienia_przegladarki, renderer=_szybki_renderer)

    app = create_app(ustawienia_przegladarki, sesje=sesje, kolejka=kolejka_natychmiastowa,
                     sprawdz_kolejke=lambda: True)
    with TestClient(app) as klient:
        yield klient


def test_scan_through_api_finds_axe_errors(klient, strona, ustawienia_przegladarki):
    skan_id = klient.post("/skany", json={"url": strona + "/index.html"}).json()["id"]

    skan = klient.get(f"/skany/{skan_id}").json()
    assert skan["status"] == "zakonczony", skan["opis_bledu"]

    [wynik] = klient.get(f"/skany/{skan_id}/wyniki").json()["podstrony"]
    assert {"image-alt", "link-name", "html-has-lang"} <= {p["regula"] for p in wynik["problemy"]}
    folder = ustawienia_przegladarki.wyniki_dir / f"skan-{skan_id}" / wynik["migawka"]
    assert (folder / "wynik.json").is_file() and (folder / "meta.json").is_file()


def test_page_blocked_by_robots_ends_with_error(klient, strona):
    skan_id = klient.post("/skany", json={"url": strona + "/prywatne/strona.html"}).json()["id"]

    skan = klient.get(f"/skany/{skan_id}").json()
    assert skan["status"] == "blad"
    assert "robots.txt" in skan["opis_bledu"]
