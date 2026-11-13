"""Test fokusu na lokalnej stronie z prawdziwym Chromium (pomijany, gdy go brak)."""

import functools
import http.server
import threading

import pytest

pytest.importorskip("playwright")

from audytor.crawler.render import Renderer, RenderOptions  # noqa: E402
from audytor.fokus.tab import mapa_fokusu, przejdz_tabem  # noqa: E402

pytestmark = pytest.mark.browser

STRONA = """<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><title>Fokus</title>
<style>
  body { font: 16px sans-serif; background: #fff; margin: 20px; }
  a, button { display: inline-block; margin: 20px; padding: 6px 12px; background: #eee; border: 0; color: #000; }
  #dobry:focus-visible { outline: 3px solid #000; outline-offset: 2px; }
  #zly:focus { outline: none; }
  #blady:focus-visible { outline: 1px solid #ddd; }
  .ukryty { position: absolute; left: -9999px; }
</style></head>
<body>
  <a id="dobry" href="#a">Dobry fokus</a>
  <button id="zly">Bez fokusu</button>
  <button id="blady">Blady fokus</button>
  <a class="ukryty" href="#b">Poza ekranem</a>
</body></html>
"""

PULAPKA = """<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><title>Pułapka</title></head>
<body>
  <a href="#x">Przed</a>
  <input id="pole" value="nie wyjdziesz">
  <a href="#y">Za</a>
  <script>
    document.getElementById('pole').addEventListener('keydown', e => {
      if (e.key === 'Tab') e.preventDefault();
    });
  </script>
</body></html>
"""


# Jak menu na wasilkow.pl: element znika w chwili otrzymania fokusu, fokus spada na <body>,
# a kolejny Tab wraca do następnego elementu.
ZGUBIONY = """<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><title>Zgubiony</title>
<style>a { display: inline-block; margin: 20px; } a:focus-visible { outline: 3px solid #000; }</style></head>
<body>
  <a id="przed" href="#x">Menu</a>
  <a id="znika" href="#y" onfocus="this.remove()">Podmenu</a>
  <a id="za" href="#z">Kontakt</a>
</body></html>
"""


class _Cichy(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("fokus")
    (root / "fokus.html").write_text(STRONA, encoding="utf-8")
    (root / "pulapka.html").write_text(PULAPKA, encoding="utf-8")
    (root / "zgubiony.html").write_text(ZGUBIONY, encoding="utf-8")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Cichy, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module")
def renderer():
    options = RenderOptions(settle_ms=100, network_idle_ms=1000, cookie_wait_ms=200, save_mhtml=False)
    try:
        r = Renderer(options)
        r.start()
    except Exception as exc:
        pytest.skip(f"Chromium niedostępny: {exc}")
    yield r
    r.close()


def test_rozpoznaje_widoczny_brak_i_slaby_fokus(site, renderer, tmp_path):
    with renderer.open(site + "/fokus.html") as opened:
        wynik = przejdz_tabem(opened.page, max_krokow=10, folder_zrzutow=tmp_path)
        mapa = mapa_fokusu(opened.page, wynik)

    werdykty = {k.selektor: k.werdykt for k in wynik.kroki}
    assert werdykty == {
        "#dobry": "ok",
        "#zly": "brak",
        "#blady": "slaby",
        "body > a:nth-of-type(2)": "niewidoczny",
    }
    # Po ostatnim elemencie fokus idzie do przeglądarki, a następny Tab wraca na początek strony –
    # to nie jest „zgubiony fokus” (werdykty wyżej nie zawierają kroku „zgubiony”).
    assert "pełny cykl" in wynik.zakonczenie or "opuścił stronę" in wynik.zakonczenie

    reguly = {p["selektor"]: p["regula"] for p in wynik.problemy}
    assert reguly == {
        "#zly": "fokus-niewidoczny",
        "#blady": "fokus-slabo-widoczny",
        "body > a:nth-of-type(2)": "fokus-poza-ekranem",
    }
    for p in wynik.problemy:
        assert p["status"] == "do_weryfikacji"
        assert p["kryteria_wcag"] == ["2.4.7"]
        assert 0 <= p["poziom_pewnosci"] <= 1

    assert (tmp_path / "01_porownanie.png").exists()
    assert mapa.width == 1366


def test_wykrywa_pulapke_klawiaturowa(site, renderer):
    with renderer.open(site + "/pulapka.html") as opened:
        wynik = przejdz_tabem(opened.page, max_krokow=10)

    assert [k.selektor for k in wynik.kroki] == ["body > a:nth-of-type(1)", "#pole"]
    assert "pułapka" in wynik.zakonczenie
    assert wynik.problemy[-1]["regula"] == "fokus-pulapka"
    assert wynik.problemy[-1]["kryteria_wcag"] == ["2.1.2"]


def test_wykrywa_zgubiony_fokus(site, renderer):
    with renderer.open(site + "/zgubiony.html") as opened:
        wynik = przejdz_tabem(opened.page, max_krokow=10)

    assert [(k.selektor, k.werdykt) for k in wynik.kroki] == [
        ("#przed", "ok"), ("body", "zgubiony"), ("#za", "ok"),
    ]
    zgubione = [p for p in wynik.problemy if p["regula"] == "fokus-zgubiony"]
    assert len(zgubione) == 1
    assert zgubione[0]["selektor"] == "#przed"     # wskazujemy element, z którego fokus „uciekł”
