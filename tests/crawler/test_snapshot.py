import json

import pytest

from audytor.crawler.snapshot import (
    PageSnapshot,
    add_base_href,
    load_meta,
    save_snapshot,
    slug_for_url,
)


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.gov.pl/", "gov-pl"),
        ("https://www.gov.pl/web/zdrowie", "gov-pl_web-zdrowie"),
        ("https://pb.edu.pl/wydzial-informatyki/", "pb-edu-pl_wydzial-informatyki"),
        ("http://localhost:8000/a.html", "localhost_a-html"),
    ],
)
def test_slug_for_url(url, expected):
    assert slug_for_url(url) == expected


def test_slug_is_limited():
    assert len(slug_for_url("https://p.pl/" + "a" * 200)) <= 60


def test_add_base_href_inserted_at_start_of_head():
    html = '<html lang="pl"><head><meta charset="utf-8"><link href="s.css"></head><body></body></html>'
    out = add_base_href(html, "https://p.pl/a/?q=1&x=2")
    assert '<head><base href="https://p.pl/a/?q=1&amp;x=2"><meta' in out


def test_add_base_href_keeps_existing_base():
    html = '<html><head><base href="/inny/"></head></html>'
    assert add_base_href(html, "https://p.pl/") == html


def test_add_base_href_without_head():
    assert add_base_href("<html><body>x</body></html>", "https://p.pl/").startswith(
        '<html><head><base href="https://p.pl/"></head>'
    )


def _snapshot(**overrides) -> PageSnapshot:
    data = dict(
        requested_url="https://p.pl",
        final_url="https://p.pl/",
        http_status=200,
        fetched_at="2026-11-03T12:00:00+00:00",
        title="Strona główna – Gmina Przykład",
        lang="pl",
        viewport={"width": 1366, "height": 768},
        user_agent="UA",
        render_ms=1234,
        robots={"robots_url": "https://p.pl/robots.txt", "status": "ok", "crawl_delay": None, "error": None},
        links_internal=["https://p.pl/kontakt"],
        links_blocked_by_robots=[],
        documents=[],
        links_external_count=3,
        dom_html="<html><head></head><body>Zażółć gęślą jaźń</body></html>",
        screenshot=b"\x89PNG fake",
        mhtml="From: <Saved by Blink>\r\nMIME-Version: 1.0\r\n",
    )
    data.update(overrides)
    return PageSnapshot(**data)


def test_save_snapshot_writes_all_files(tmp_path):
    folder = save_snapshot(_snapshot(), tmp_path)
    assert folder == tmp_path / "p-pl"
    assert (folder / "dom.html").read_text(encoding="utf-8").endswith("Zażółć gęślą jaźń</body></html>")
    assert (folder / "screenshot.png").read_bytes() == b"\x89PNG fake"
    assert b"\r\n" in (folder / "page.mhtml").read_bytes()  # CRLF zachowane

    meta = load_meta(folder)
    assert meta["schema_version"] == "1.0"
    assert meta["title"] == "Strona główna – Gmina Przykład"
    assert meta["links"]["internal"] == ["https://p.pl/kontakt"]
    assert meta["files"] == {"dom": "dom.html", "screenshot": "screenshot.png", "mhtml": "page.mhtml"}
    # polskie znaki zapisane wprost, nie jako ą
    assert "ł" in (folder / "meta.json").read_text(encoding="utf-8")


def test_resave_as_jpeg_without_mhtml_removes_stale_files(tmp_path):
    save_snapshot(_snapshot(), tmp_path, name="x")
    folder = save_snapshot(_snapshot(screenshot_type="jpeg", mhtml=None), tmp_path, name="x")
    names = sorted(p.name for p in folder.iterdir())
    assert names == ["dom.html", "meta.json", "screenshot.jpg"]
    assert json.loads((folder / "meta.json").read_text(encoding="utf-8"))["files"]["screenshot"] == "screenshot.jpg"
