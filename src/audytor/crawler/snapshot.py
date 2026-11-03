"""Migawka strony i jej zapis na dysk – format opisany w docs/kontrakt-danych.md (sekcja 1)."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA_VERSION = "1.0"

DOM_FILE = "dom.html"
MHTML_FILE = "page.mhtml"
META_FILE = "meta.json"
SCREENSHOT_FILES = {"png": "screenshot.png", "jpeg": "screenshot.jpg"}
BANNER_SCREENSHOT_FILES = {"png": "screenshot-baner.png", "jpeg": "screenshot-baner.jpg"}


@dataclass
class PageSnapshot:
    """Wszystko, co crawler wie o jednej wyrenderowanej stronie."""

    requested_url: str
    final_url: str
    http_status: int | None
    fetched_at: str                      # ISO 8601, UTC
    title: str
    lang: str
    viewport: dict                       # {"width": ..., "height": ...}
    user_agent: str
    render_ms: int
    robots: dict
    links_internal: list[str]
    links_blocked_by_robots: list[str]
    documents: list[str]
    links_external_count: int
    dom_html: str
    screenshot: bytes
    screenshot_type: str = "png"         # "png" albo "jpeg"
    mhtml: str | None = None
    cookie_banner: dict = field(default_factory=lambda: {"checked": False})
    cookie_banner_screenshot: bytes | None = None   # widok okna z banerem, przed jego zamknięciem
    warnings: list[str] = field(default_factory=list)

    def meta(self) -> dict:
        files = {"dom": DOM_FILE, "screenshot": SCREENSHOT_FILES[self.screenshot_type]}
        if self.mhtml is not None:
            files["mhtml"] = MHTML_FILE
        if self.cookie_banner_screenshot is not None:
            files["cookie_banner_screenshot"] = BANNER_SCREENSHOT_FILES[self.screenshot_type]
        return {
            "schema_version": SCHEMA_VERSION,
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "http_status": self.http_status,
            "fetched_at": self.fetched_at,
            "title": self.title,
            "lang": self.lang,
            "viewport": self.viewport,
            "user_agent": self.user_agent,
            "render_ms": self.render_ms,
            "robots": self.robots,
            "links": {
                "internal": self.links_internal,
                "blocked_by_robots": self.links_blocked_by_robots,
                "documents": self.documents,
                "external_count": self.links_external_count,
            },
            "cookie_banner": self.cookie_banner,
            "files": files,
            "warnings": self.warnings,
        }


def slug_for_url(url: str, max_length: int = 60) -> str:
    """Nazwa folderu migawki z adresu: https://www.gov.pl/web/zdrowie -> gov-pl_web-zdrowie."""
    parts = urlsplit(url)
    host = (parts.hostname or "strona").lower()
    if host.startswith("www."):
        host = host[4:]
    slug = re.sub(r"[^a-z0-9]+", "-", host).strip("-")
    path = re.sub(r"[^a-z0-9]+", "-", parts.path.lower()).strip("-")
    if path:
        slug = f"{slug}_{path}"
    return slug[:max_length].rstrip("-_") or "strona"


_BASE_RE = re.compile(r"<base\s[^>]*href", re.IGNORECASE)
_HEAD_RE = re.compile(r"<head(\s[^>]*)?>", re.IGNORECASE)
_HTML_RE = re.compile(r"<html(\s[^>]*)?>", re.IGNORECASE)


def add_base_href(document: str, url: str) -> str:
    """Wstawia <base href> na początek <head>, żeby zapisany DOM otwarty z dysku
    ładował CSS i obrazki z oryginalnej witryny. Istniejącego <base> nie zmienia."""
    if _BASE_RE.search(document):
        return document
    tag = f'<base href="{html.escape(url, quote=True)}">'
    match = _HEAD_RE.search(document)
    if match:
        return document[: match.end()] + tag + document[match.end():]
    match = _HTML_RE.search(document)
    if match:
        return document[: match.end()] + f"<head>{tag}</head>" + document[match.end():]
    return f"<head>{tag}</head>" + document


def save_snapshot(snapshot: PageSnapshot, out_dir: str | Path, name: str | None = None) -> Path:
    """Zapisuje migawkę do `out_dir/<name>/` i zwraca ścieżkę folderu.

    Istniejące pliki migawki w tym folderze są nadpisywane.
    """
    folder = Path(out_dir) / (name or slug_for_url(snapshot.final_url or snapshot.requested_url))
    folder.mkdir(parents=True, exist_ok=True)

    # Usuń zrzut w innym formacie z poprzedniego zapisu, żeby nie zostały dwa.
    for other in (*SCREENSHOT_FILES.values(), *BANNER_SCREENSHOT_FILES.values()):
        (folder / other).unlink(missing_ok=True)
    if snapshot.mhtml is None:
        (folder / MHTML_FILE).unlink(missing_ok=True)

    (folder / DOM_FILE).write_text(snapshot.dom_html, encoding="utf-8")
    (folder / SCREENSHOT_FILES[snapshot.screenshot_type]).write_bytes(snapshot.screenshot)
    if snapshot.cookie_banner_screenshot is not None:
        (folder / BANNER_SCREENSHOT_FILES[snapshot.screenshot_type]).write_bytes(snapshot.cookie_banner_screenshot)
    if snapshot.mhtml is not None:
        # newline="" – MHTML ma własne końce linii (CRLF), nie wolno ich zmieniać
        with open(folder / MHTML_FILE, "w", encoding="utf-8", newline="") as fh:
            fh.write(snapshot.mhtml)
    (folder / META_FILE).write_text(
        json.dumps(snapshot.meta(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return folder


def load_meta(folder: str | Path) -> dict:
    """Wczytuje meta.json migawki (pomocnicze dla innych modułów)."""
    return json.loads((Path(folder) / META_FILE).read_text(encoding="utf-8"))
