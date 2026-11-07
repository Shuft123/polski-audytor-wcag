"""axe-core i komenda „skanuj adres” na lokalnym serwerze HTTP (prawdziwy Chromium, bez internetu).

Pomijany automatycznie, jeśli Playwright albo przeglądarka Chromium nie są zainstalowane.
"""

import functools
import http.server
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright")
pytest.importorskip("axe_playwright_python")

from audytor.axe import axe_na_problemy, uruchom_axe, wersja_axe  # noqa: E402
from audytor.crawler.render import Renderer, RenderOptions  # noqa: E402
from audytor.crawler.snapshot import load_meta  # noqa: E402
from audytor.skan import skanuj_strone  # noqa: E402
from audytor.wyniki import wczytaj_wynik  # noqa: E402

pytestmark = pytest.mark.browser

Z_BLEDAMI = """<!doctype html>
<html><head><meta charset="utf-8"><title>Gmina z błędami</title></head>
<body>
<h1>Gmina</h1>
<img src="herb.png">
<img src="logo.png" alt="Logo gminy">
<a href="/aktualnosci"></a>
<form><input type="text" id="szukaj"></form>
<p style="color:#bbb;background:#fff">Słaby kontrast</p>
</body></html>
"""

POPRAWNA = """<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><title>Gmina bez błędów</title></head>
<body><main><h1>Gmina</h1>
<img src="herb.png" alt="Herb gminy">
<a href="/aktualnosci">Aktualności</a>
<form><label for="q">Szukaj</label><input type="text" id="q"></form>
</main></body></html>
"""

# Treść dodana przez JavaScript – axe musi ją zobaczyć (działa na wyrenderowanej stronie).
Z_JS = """<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><title>JS</title></head>
<body><main><h1>Gmina</h1><div id="tu"></div></main>
<script>document.getElementById('tu').innerHTML = '<img src="z-js.png">';</script>
</body></html>
"""

FILES = {
    "bledy.html": Z_BLEDAMI,
    "poprawna.html": POPRAWNA,
    "js.html": Z_JS,
    "robots.txt": "User-agent: *\nDisallow: /prywatne/\n",
}


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("strona-axe")
    for name, content in FILES.items():
        (root / name).write_text(content, encoding="utf-8")
    handler = functools.partial(_QuietHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module")
def renderer():
    options = RenderOptions(settle_ms=100, network_idle_ms=1000, cookie_wait_ms=500, save_mhtml=False)
    try:
        r = Renderer(options)
        r.start()
    except Exception as exc:  # brak Chromium -> pomiń zamiast failować
        pytest.skip(f"Chromium niedostępny: {exc}")
    yield r
    r.close()


def _reguly(wynik_axe, typ="violations"):
    return {r["id"] for r in wynik_axe[typ]}


def test_axe_finds_typical_errors(site, renderer):
    with renderer.open(site + "/bledy.html") as opened:
        wynik_axe = uruchom_axe(opened.page)
    assert {"image-alt", "link-name", "label", "html-has-lang", "color-contrast"} <= _reguly(wynik_axe)
    assert wynik_axe["testEngine"]["version"] == wersja_axe()


def test_axe_on_correct_page_finds_nothing(site, renderer):
    with renderer.open(site + "/poprawna.html") as opened:
        wynik_axe = uruchom_axe(opened.page)
    assert wynik_axe["violations"] == []


def test_axe_sees_content_rendered_by_javascript(site, renderer):
    with renderer.open(site + "/js.html") as opened:
        problemy = axe_na_problemy(uruchom_axe(opened.page), opened.final_url)
    alt = [p for p in problemy if p.regula == "image-alt"]
    assert len(alt) == 1 and 'src="z-js.png"' in alt[0].fragment_html


def test_axe_messages_polish_by_default_english_on_request(site, renderer):
    with renderer.open(site + "/bledy.html") as opened:
        po_polsku = uruchom_axe(opened.page)
        po_angielsku = uruchom_axe(opened.page, jezyk=None)
    pomoc = {r["id"]: r["help"] for r in po_polsku["violations"]}
    assert pomoc["image-alt"] == "Obrazy muszą mieć tekst alternatywny."
    assert {r["id"]: r["help"] for r in po_angielsku["violations"]}["image-alt"] == "Images must have alternative text"


def test_only_wcag_a_and_aa_rules_are_run(site, renderer):
    with renderer.open(site + "/bledy.html") as opened:
        wynik_axe = uruchom_axe(opened.page)
    # "region" to reguła best-practice – nie należy do WCAG, więc nie może się pojawić
    assert "region" not in _reguly(wynik_axe)
    for regula in wynik_axe["violations"]:
        assert {"wcag2a", "wcag2aa", "wcag21a", "wcag21aa"} & set(regula["tags"])


def test_skanuj_strone_saves_snapshot_and_result(site, renderer, tmp_path):
    wynik, folder = skanuj_strone(renderer, site + "/bledy.html", tmp_path)

    assert (folder / "dom.html").is_file()
    assert load_meta(folder)["final_url"] == wynik.url
    zapisany = wczytaj_wynik(folder)
    assert zapisany.to_dict() == wynik.to_dict()
    assert zapisany.migawka == folder.name
    assert zapisany.narzedzia["axe-core"] == wersja_axe()
    assert zapisany.podsumowanie()["wg_statusu"]["blad"] >= 5
    assert all(p.url_podstrony == wynik.url for p in zapisany.problemy)


def _audytor_scan(*args: str) -> subprocess.CompletedProcess:
    # Osobny proces: CLI uruchamia własną przeglądarkę, a dwie instancje sync_playwright
    # nie mogą działać w jednym wątku (fixture `renderer` jest już uruchomiony).
    src = str(Path(__file__).resolve().parents[2] / "src")
    env = {**os.environ, "PYTHONPATH": src + os.pathsep + os.environ.get("PYTHONPATH", ""),
           # Na Windows podproces pisze do potoku w cp1250 – wymuszamy UTF-8, bo czytamy polskie komunikaty.
           "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    return subprocess.run([sys.executable, "-m", "audytor.skan", *args],
                          capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)


def test_cli_scan_with_database(site, tmp_path):
    baza = tmp_path / "audytor.db"
    proces = _audytor_scan(site + "/bledy.html", site + "/poprawna.html", "--out", str(tmp_path / "wyniki"),
                           "--db", f"sqlite:///{baza}", "--delay", "0")
    assert proces.returncode == 0, proces.stderr
    assert "Gotowe: 2 z 2" in proces.stdout
    assert "Zapisano w bazie: skan #1, podstron: 2." in proces.stdout

    dane = json.loads((tmp_path / "wyniki" / "127-0-0-1_poprawna-html" / "wynik.json").read_text(encoding="utf-8"))
    assert dane["podsumowanie"]["wg_statusu"]["blad"] == 0

    from audytor.db import Skan, otworz_baze

    with otworz_baze(f"sqlite:///{baza}")() as sesja:
        skan = sesja.get(Skan, 1)
        assert [len(p.problemy) > 0 for p in skan.podstrony] == [True, False]


def test_cli_reports_page_blocked_by_robots(site, tmp_path):
    proces = _audytor_scan(site + "/prywatne/panel.html", "--out", str(tmp_path))
    assert proces.returncode == 1
    assert "POMINIĘTO" in proces.stderr
