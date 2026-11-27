"""Crawling wielu podstron (F1, F2): logika bez przeglądarki + pełny przebieg na lokalnej witrynie."""

import http.server
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from audytor.crawler.links import strip_tracking

# --- bez przeglądarki ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://p.pl/a?utm_source=fb&utm_medium=x", "https://p.pl/a"),
        ("https://p.pl/a?id=5&fbclid=abc&gclid=1", "https://p.pl/a?id=5"),
        ("https://p.pl/a?UTM_Campaign=z&strona=2", "https://p.pl/a?strona=2"),
        ("https://p.pl/a?id=5", "https://p.pl/a?id=5"),
        ("https://p.pl/a", "https://p.pl/a"),
    ],
)
def test_strip_tracking(url, expected):
    assert strip_tracking(url) == expected


class FakeClock:
    def __init__(self):
        self.t = 100.0
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def test_rate_limiter_waits_per_host():
    pytest.importorskip("playwright")
    from audytor.crawler.crawl import RateLimiter

    clock = FakeClock()
    limiter = RateLimiter(1.0, clock=clock, sleep=clock.sleep)
    assert limiter.wait("https://www.p.pl/a") == 0          # pierwsza strona – bez pauzy
    limiter.visited("https://www.p.pl/a")
    clock.t += 0.3
    assert limiter.wait("https://p.pl/b") == pytest.approx(0.7)   # www. bez znaczenia – ten sam host
    limiter.visited("https://p.pl/b")
    assert limiter.wait("https://inna.pl/") == 0             # inna witryna – bez pauzy


def test_rate_limiter_uses_bigger_crawl_delay():
    pytest.importorskip("playwright")
    from audytor.crawler.crawl import RateLimiter

    clock = FakeClock()
    limiter = RateLimiter(1.0, crawl_delay=lambda url: 3.0, clock=clock, sleep=clock.sleep)
    limiter.visited("https://p.pl/")
    assert limiter.wait("https://p.pl/x") == pytest.approx(3.0)
    small = RateLimiter(2.0, crawl_delay=lambda url: 0.5, clock=clock, sleep=clock.sleep)
    small.visited("https://p.pl/")
    assert small.wait_time("https://p.pl/x") == pytest.approx(2.0)


@pytest.mark.parametrize("kwargs", [{"max_depth": -1}, {"max_depth": 11}, {"max_pages": 0},
                                    {"max_pages": 501}, {"delay_s": -1}])
def test_crawl_options_validation(kwargs):
    pytest.importorskip("playwright")
    from audytor.crawler.crawl import CrawlOptions

    with pytest.raises(ValueError):
        CrawlOptions(**kwargs)


# --- lokalna witryna z pułapkami -------------------------------------------------------------------

def _html(title, links=()):
    a = "".join(f'<a href="{h}">{h}</a> ' for h in links)
    return f"<!doctype html><html lang='pl'><head><meta charset='utf-8'><title>{title}</title></head><body><h1>{title}</h1>{a}</body></html>"


PAGES = {
    "/": _html("Start", [
        "/a.html", "/b.html?utm_source=newsletter", "/b.html", "/a.html#gora",   # duplikaty
        "/prywatne/x.html",                                                       # robots.txt
        "https://example.com/",                                                   # zewnętrzny
        "/pliki/plan.pdf",                                                        # dokument
        "/stary",                                                                 # 301 -> /a.html
        "/zewn",                                                                  # 302 -> inny host
        "/pobierz",                                                               # plik do pobrania
        "/brak",                                                                  # 404
    ]),
    "/a.html": _html("A", ["/c.html", "/", "/b.html"]),
    "/b.html": _html("B", ["/d.html"]),
    "/c.html": _html("C", ["/e.html"]),       # e.html jest na głębokości 3 – poza limitem 2
    "/d.html": _html("D"),
    "/e.html": _html("E"),
    "/robots.txt": "User-agent: *\nDisallow: /prywatne/\n",
}


class _Handler(http.server.BaseHTTPRequestHandler):
    other_host = ""
    requests: list = []

    def log_message(self, *args):
        pass

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        type(self).requests.append(path)
        if path == "/stary":
            self._redirect(301, "/a.html")
        elif path == "/zewn":
            self._redirect(302, self.other_host + "/")
        elif path == "/pobierz":
            body = b"%PDF-1.4 test"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", "attachment; filename=plik.bin")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path in PAGES:
            self._send(200, PAGES[path], "text/plain" if path.endswith(".txt") else "text/html")
        else:
            self._send(404, _html("Nie znaleziono", ["/d.html"]), "text/html")

    def _redirect(self, code, location):
        self.send_response(code)
        self.send_header("Location", location)
        self.end_headers()

    def _send(self, code, text, ctype):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def site():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    _Handler.other_host = f"http://localhost:{port}"   # inny host = inna witryna
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture(scope="module")
def renderer():
    pytest.importorskip("playwright")
    from audytor.crawler.render import Renderer, RenderOptions

    options = RenderOptions(settle_ms=50, network_idle_ms=500, cookie_wait_ms=0, scroll=False,
                            screenshot_type="jpeg", save_mhtml=False, timeout_ms=10_000)
    try:
        r = Renderer(options)
        r.start()
    except Exception as exc:  # brak Chromium -> pomiń
        pytest.skip(f"Chromium niedostępny: {exc}")
    yield r
    r.close()


def _crawl(renderer, site, out=None, **kwargs):
    from audytor.crawler.crawl import CrawlOptions, SiteCrawler

    kwargs.setdefault("delay_s", 0)
    kwargs.setdefault("save_snapshots", out is not None)
    return SiteCrawler(renderer, CrawlOptions(**kwargs)).crawl(site + "/", out_dir=out)


@pytest.mark.browser
def test_full_crawl_of_small_site(site, renderer, tmp_path):
    from audytor.crawler.crawl import load_crawl

    result = _crawl(renderer, site, tmp_path, max_depth=2, max_pages=50)

    assert result.stop_reason == "kolejka_pusta"
    assert result.page_urls() == [f"{site}/", f"{site}/a.html", f"{site}/b.html", f"{site}/c.html", f"{site}/d.html"]
    by_url = {p.url: p for p in result.pages}

    # przekierowanie na już odwiedzoną stronę = jedna strona
    assert by_url[f"{site}/stary"].status == "pominieta"
    assert "ta sama strona" in by_url[f"{site}/stary"].reason
    # przekierowanie na inny host = poza witryną
    assert by_url[f"{site}/zewn"].status == "pominieta"
    assert "poza witrynę" in by_url[f"{site}/zewn"].reason
    # plik zamiast strony = błąd, crawl idzie dalej
    assert by_url[f"{site}/pobierz"].status == "blad"
    # strona 404: zapisana, ale jej linków nie śledzimy
    assert by_url[f"{site}/brak"].http_status == 404
    assert by_url[f"{site}/brak"].new_links == 0
    # głębokość: e.html (głębokość 3) nie trafia nawet do kolejki
    assert f"{site}/e.html" not in by_url
    assert by_url[f"{site}/c.html"].depth == 2
    # deduplikacja: b.html z utm_ i bez to jedna strona, a.html#gora to a.html
    assert sum(1 for p in result.pages if "b.html" in p.url) == 1
    assert sum(1 for p in result.pages if "a.html" in p.url) == 1

    assert result.blocked_by_robots == [f"{site}/prywatne/x.html"]
    assert result.documents == [f"{site}/pliki/plan.pdf"]
    assert "/prywatne/x.html" not in _Handler.requests      # do zablokowanej strony nie było zapytania

    # migawki + crawl.json
    assert by_url[f"{site}/"].snapshot == "127-0-0-1"
    assert (tmp_path / "127-0-0-1" / "meta.json").exists()
    dane = load_crawl(tmp_path)
    assert dane["summary"]["ok"] == 6 and dane["summary"]["max_glebokosc"] == 2
    assert dane["options"]["max_depth"] == 2


@pytest.mark.browser
def test_max_pages_limit(site, renderer):
    result = _crawl(renderer, site, max_depth=5, max_pages=3)
    assert result.stop_reason == "limit_stron"
    assert len(result.pages) == 3
    assert result.not_visited and all(n["reason"] == "limit stron" for n in result.not_visited)


@pytest.mark.browser
def test_depth_zero_is_start_page_only(site, renderer):
    result = _crawl(renderer, site, max_depth=0)
    assert result.page_urls() == [f"{site}/"]
    assert result.stop_reason == "kolejka_pusta"


@pytest.mark.browser
def test_start_page_blocked_by_robots(site, renderer):
    from audytor.crawler.crawl import CrawlOptions, SiteCrawler

    _Handler.requests.clear()
    result = SiteCrawler(renderer, CrawlOptions(delay_s=0, save_snapshots=False)).crawl(site + "/prywatne/x.html")
    assert result.stop_reason == "strona_startowa_niedostepna"
    assert result.pages[0].status == "pominieta"
    assert "/prywatne/x.html" not in _Handler.requests


@pytest.mark.browser
def test_on_page_gets_live_page_and_hook_errors_do_not_stop(site, renderer):
    from audytor.crawler.crawl import CrawlOptions, SiteCrawler

    headings = []

    def hook(opened, page):
        headings.append(opened.page.locator("h1").inner_text())
        if page.url.endswith("/a.html"):
            raise RuntimeError("awaria haka")

    result = SiteCrawler(renderer, CrawlOptions(max_depth=1, delay_s=0, save_snapshots=False)).crawl(
        site + "/", on_page=hook)
    assert headings[:3] == ["Start", "A", "B"]
    a = next(p for p in result.pages if p.url.endswith("/a.html"))
    assert a.status == "ok" and any("awaria haka" in w for w in a.warnings)


@pytest.mark.browser
def test_rate_limit_respects_crawl_delay(site, renderer):
    from audytor.crawler.crawl import CrawlOptions, SiteCrawler
    from audytor.crawler.robots import parse_robots, robots_url_for

    # Crawl-delay: 1 z robots.txt; delay_s = 0, więc pauzy biorą się tylko z robots.txt
    renderer.robots._cache[robots_url_for(site)] = parse_robots(
        "User-agent: *\nDisallow: /prywatne/\nCrawl-delay: 1\n", robots_url_for(site))
    slept = []
    try:
        SiteCrawler(renderer, CrawlOptions(max_depth=1, max_pages=3, delay_s=0, save_snapshots=False),
                    sleep=slept.append).crawl(site + "/")
    finally:
        renderer.robots._cache.pop(robots_url_for(site))
    assert len(slept) == 2 and all(0.5 < s <= 1.0 for s in slept)


@pytest.mark.browser
def test_cli_crawl(site, tmp_path):
    src = Path(__file__).resolve().parents[2] / "src"
    env = {**os.environ, "PYTHONPATH": str(src), "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, "-m", "audytor.crawler", site + "/", "--crawl", "--depth", "1", "--max-pages", "4",
         "--out", str(tmp_path), "--name", "lokalna", "--delay", "0", "--jpeg", "--no-mhtml", "--no-scroll"],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Koniec: osiągnięto limit stron" in proc.stdout
    assert (tmp_path / "lokalna" / "crawl.json").exists()
    assert (tmp_path / "lokalna" / "127-0-0-1" / "screenshot.jpg").exists()


def test_cli_no_snapshots_requires_crawl():
    src = Path(__file__).resolve().parents[2] / "src"
    env = {**os.environ, "PYTHONPATH": str(src), "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run([sys.executable, "-m", "audytor.crawler", "https://p.pl/", "--no-snapshots"],
                          capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
    assert proc.returncode == 2 and "--no-snapshots" in proc.stderr
