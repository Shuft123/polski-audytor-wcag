"""Test całego przebiegu na lokalnym serwerze HTTP (bez internetu, ale z prawdziwym Chromium).

Pomijany automatycznie, jeśli Playwright albo przeglądarka Chromium nie są zainstalowane.
"""

import functools
import http.server
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from audytor.crawler.render import Renderer, RenderOptions, RobotsDisallowedError  # noqa: E402
from audytor.crawler.snapshot import load_meta, save_snapshot  # noqa: E402

pytestmark = pytest.mark.browser

INDEX = """<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><title>Gmina Testowa</title>
<link rel="stylesheet" href="styl.css"></head>
<body>
<h1>Witamy w Gminie Testowej</h1>
<p id="js">bez JS</p>
<a href="/kontakt.html">Kontakt</a>
<a href="kontakt.html#mapa">Kontakt (mapa)</a>
<a href="/prywatne/panel.html">Panel</a>
<a href="/pliki/deklaracja.pdf">Deklaracja</a>
<a href="https://example.com/">Zewnętrzny</a>
<a href="mailto:urzad@gmina.pl">E-mail</a>
<script>document.getElementById('js').textContent = 'wyrenderowane przez JS';</script>
</body></html>
"""

FILES = {
    "index.html": INDEX,
    "kontakt.html": "<html lang='pl'><head><title>Kontakt</title></head><body>Kontakt</body></html>",
    "styl.css": "body { font-family: sans-serif; }",
    "robots.txt": "User-agent: *\nDisallow: /prywatne/\n",
    "prywatne/panel.html": "<html><body>tajne</body></html>",
    "dluga.html": "<html><body style='margin:0'><div style='height:6000px;background:#eee'>długa</div></body></html>",
    # baner z przyciskiem odrzucenia – po kliknięciu znika i zapisuje decyzję
    "cookies.html": """<!doctype html><html lang="pl"><head><meta charset="utf-8"><title>Z banerem</title></head>
<body><h1>Treść strony</h1>
<div id="baner" role="dialog" style="position:fixed;bottom:0;left:0;right:0;height:200px;background:#333;color:#fff">
  <p>Używamy plików cookies, aby strona działała poprawnie.</p>
  <button onclick="window.zgoda='wszystkie';document.getElementById('baner').remove()">Akceptuję wszystkie</button>
  <button onclick="window.zgoda='odrzucone';document.getElementById('baner').remove()">Odrzuć wszystkie</button>
</div></body></html>""",
    # baner bez możliwości odrzucenia – nie wolno kliknąć "Akceptuję"
    "cookies-tylko-akceptuj.html": """<!doctype html><html lang="pl"><head><meta charset="utf-8"><title>Tylko akceptuj</title></head>
<body><h1>Treść</h1>
<div style="position:fixed;top:0;left:0;right:0;height:150px;background:#eee">
  Ta strona używa ciasteczek. <button onclick="window.zgoda='wszystkie'">Akceptuję</button>
</div></body></html>""",
    # baner pojawia się z opóźnieniem (jak na x-kom.pl)
    "cookies-opoznione.html": """<!doctype html><html lang="pl"><head><meta charset="utf-8"><title>Opóźniony</title></head>
<body><h1>Treść</h1><script>
setTimeout(() => {
  const d = document.createElement('div');
  d.id = 'baner'; d.style.cssText = 'position:fixed;bottom:0;left:0;right:0;height:180px;background:#ddd';
  d.innerHTML = 'Korzystamy z ciasteczek. <button id="ok">Akceptuję wszystkie</button> '
    + '<button id="nie">Odrzucam niewymagane</button>';
  document.body.appendChild(d);
  document.getElementById('nie').onclick = () => { window.zgoda = 'odrzucone'; d.remove(); };
}, 600);
</script></body></html>""",
    # przycisk "Odrzuć" poza banerem cookies – nie wolno go kliknąć
    "formularz.html": """<!doctype html><html lang="pl"><head><meta charset="utf-8"><title>Formularz</title></head>
<body><form><textarea>komentarz</textarea>
<button type="button" onclick="window.klik=true">Odrzuć</button></form></body></html>""",
}


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("strona")
    for name, content in FILES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    handler = functools.partial(_QuietHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module")
def renderer():
    options = RenderOptions(settle_ms=100, network_idle_ms=1000, cookie_wait_ms=1000)
    try:
        r = Renderer(options)
        r.start()
    except Exception as exc:  # brak Chromium -> pomiń zamiast failować
        pytest.skip(f"Chromium niedostępny: {exc}")
    yield r
    r.close()


def test_render_page_collects_everything(site, renderer, tmp_path):
    snapshot = renderer.render(site + "/index.html")

    assert snapshot.http_status == 200
    assert snapshot.title == "Gmina Testowa"
    assert snapshot.lang == "pl"
    assert "wyrenderowane przez JS" in snapshot.dom_html          # DOM po wykonaniu JS
    assert f'<base href="{site}/index.html">' in snapshot.dom_html
    assert snapshot.screenshot[:4] == b"\x89PNG"
    assert snapshot.mhtml and "Gmina Testowa" in snapshot.mhtml
    assert snapshot.links_internal == [f"{site}/kontakt.html"]
    assert snapshot.links_blocked_by_robots == [f"{site}/prywatne/panel.html"]
    assert snapshot.documents == [f"{site}/pliki/deklaracja.pdf"]
    assert snapshot.links_external_count == 1
    assert snapshot.robots["status"] == "ok"
    assert "PolskiAudytorWCAG/" in snapshot.user_agent

    folder = save_snapshot(snapshot, tmp_path)
    assert load_meta(folder)["final_url"] == f"{site}/index.html"


def test_open_gives_live_page_for_other_modules(site, renderer):
    with renderer.open(site + "/index.html") as opened:
        # Tu np. moduł axe-core uruchamia się na żywej stronie.
        assert opened.page.locator("h1").inner_text() == "Witamy w Gminie Testowej"
        snapshot = renderer.capture(opened)
    assert snapshot.title == "Gmina Testowa"


def test_robots_blocks_disallowed_page(site, renderer):
    with pytest.raises(RobotsDisallowedError):
        renderer.render(site + "/prywatne/panel.html")


def test_http_error_is_reported_as_warning(site, renderer):
    snapshot = renderer.render(site + "/nie-ma-takiej.html")
    assert snapshot.http_status == 404
    assert any("404" in w for w in snapshot.warnings)


def test_very_long_page_is_clipped(site, renderer):
    renderer.options.max_screenshot_height = 2000
    try:
        snapshot = renderer.render(site + "/dluga.html")
    finally:
        renderer.options.max_screenshot_height = RenderOptions().max_screenshot_height
    png_height = int.from_bytes(snapshot.screenshot[20:24], "big")  # nagłówek IHDR
    assert png_height == 2000
    assert any("przycięty" in w for w in snapshot.warnings)


def test_cli_reports_browser_start_failure(tmp_path):
    # Nieistniejący kanał przeglądarki -> czytelny komunikat i kod 3 zamiast tracebacku.
    src = Path(__file__).resolve().parents[2] / "src"
    env = {**os.environ, "PYTHONPATH": str(src), "PYTHONIOENCODING": "utf-8",
           "PLAYWRIGHT_BROWSERS_PATH": str(tmp_path / "brak-przegladarek")}
    proc = subprocess.run(
        [sys.executable, "-m", "audytor.crawler", "https://example.com/", "--out", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=120,
    )
    assert proc.returncode == 3
    assert "Nie udało się uruchomić przeglądarki" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_end_to_end(site, tmp_path):
    # Osobny proces: tak jak uruchamia to użytkownik (python -m audytor.crawler ...).
    src = Path(__file__).resolve().parents[2] / "src"
    env = {**os.environ, "PYTHONPATH": str(src), "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, "-m", "audytor.crawler", site + "/index.html", site + "/prywatne/panel.html",
         "--out", str(tmp_path), "--delay", "0", "--jpeg", "--no-mhtml"],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=120,
    )
    assert proc.returncode == 1, proc.stderr   # jedna strona zablokowana przez robots.txt
    assert "POMINIĘTO" in proc.stderr
    assert "Gotowe: 1 z 2" in proc.stdout
    folder = tmp_path / "127-0-0-1_index-html"
    assert sorted(p.name for p in folder.iterdir()) == ["dom.html", "meta.json", "screenshot.jpg"]


def test_cookie_banner_is_rejected_and_recorded(site, renderer):
    with renderer.open(site + "/cookies.html") as opened:
        assert opened.page.evaluate("window.zgoda") == "odrzucone"
        snapshot = renderer.capture(opened)
    info = snapshot.cookie_banner
    assert info["detected"] and info["dismissed"]
    assert info["button_text"] == "odrzuć wszystkie"
    assert snapshot.cookie_banner_screenshot[:4] == b"\x89PNG"     # zrzut z banerem zapisany
    assert "Używamy plików cookies" not in snapshot.dom_html         # migawka już bez banera
    assert "data-audytor-cookie" not in snapshot.dom_html            # znacznik usunięty


def test_cookie_banner_without_reject_is_left_alone(site, renderer):
    with renderer.open(site + "/cookies-tylko-akceptuj.html") as opened:
        assert opened.page.evaluate("window.zgoda") is None             # "Akceptuję" NIE kliknięte
        snapshot = renderer.capture(opened)
    assert snapshot.cookie_banner["detected"] and not snapshot.cookie_banner["dismissed"]
    assert snapshot.cookie_banner_screenshot is not None
    assert any("nie znaleziono przycisku odrzucenia" in w for w in snapshot.warnings)


def test_reject_button_outside_cookie_banner_is_not_clicked(site, renderer):
    with renderer.open(site + "/formularz.html") as opened:
        assert opened.page.evaluate("window.klik") is None
        snapshot = renderer.capture(opened)
    assert snapshot.cookie_banner == {"checked": True, "detected": False, "dismissed": False,
                                      "method": None, "button_text": None, "frame_url": None}
    assert snapshot.cookie_banner_screenshot is None


def test_keep_cookie_banner_option(site, renderer, tmp_path):
    renderer.options.dismiss_cookies = False
    try:
        with renderer.open(site + "/cookies.html") as opened:
            assert opened.page.evaluate("window.zgoda") is None
            snapshot = renderer.capture(opened)
    finally:
        renderer.options.dismiss_cookies = True
    assert snapshot.cookie_banner == {"checked": False}
    assert "Używamy plików cookies" in snapshot.dom_html
    folder = save_snapshot(snapshot, tmp_path)
    assert "cookie_banner_screenshot" not in load_meta(folder)["files"]


def test_delayed_cookie_banner_is_handled(site, renderer):
    with renderer.open(site + "/cookies-opoznione.html") as opened:
        assert opened.page.evaluate("window.zgoda") == "odrzucone"
        snapshot = renderer.capture(opened)
    assert snapshot.cookie_banner["dismissed"]
    assert snapshot.cookie_banner["button_text"] == "odrzucam niewymagane"
