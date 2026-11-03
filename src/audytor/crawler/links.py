"""Normalizacja adresów i podział linków na wewnętrzne / zewnętrzne (F1, wersja 1 poziom)."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit, urlunsplit

# Linki do dokumentów zbieramy osobno – przydadzą się w audycie PDF/DOCX (F25, F26).
DOCUMENT_EXTENSIONS = (
    ".pdf", ".doc", ".docx", ".odt", ".rtf",
    ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp",
)
# Pliki, które nie są stronami ani dokumentami – pomijamy.
SKIPPED_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp",
    ".zip", ".rar", ".7z", ".gz", ".tar",
    ".mp3", ".wav", ".mp4", ".avi", ".mov", ".webm",
    ".css", ".js", ".xml", ".json",
)
_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_url(url: str | None, base: str | None = None) -> str | None:
    """Zwraca znormalizowany adres http(s) albo None, gdy adres nie jest stroną WWW.

    Normalizacja: rozwiązanie adresu względnego, małe litery w schemacie i hoście,
    usunięcie domyślnego portu i fragmentu (#...), pusta ścieżka -> "/".
    Odrzucane: mailto:, tel:, javascript:, data:, ftp: itd.
    """
    if url is None:
        return None
    url = url.strip()
    if not url:
        return None
    try:
        if base:
            url = urljoin(base, url)
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None

    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        return None
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        return None

    netloc = host if port in (None, _DEFAULT_PORTS[scheme]) else f"{host}:{port}"
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def site_host(url: str) -> str:
    """Host bez przedrostka "www." – www.example.pl i example.pl to ta sama witryna."""
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def is_internal(url: str, site_url: str) -> bool:
    """Czy adres należy do tej samej witryny (ten sam host; poddomeny NIE są wliczane)."""
    return site_host(url) == site_host(site_url)


def _extension(url: str) -> str:
    last = urlsplit(url).path.lower().rsplit("/", 1)[-1]
    return "." + last.rsplit(".", 1)[-1] if "." in last else ""


@dataclass
class LinkSet:
    """Wynik podziału linków znalezionych na stronie."""

    pages: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    external_count: int = 0


def classify_links(hrefs: list[str], page_url: str) -> LinkSet:
    """Dzieli linki ze strony na podstrony wewnętrzne i dokumenty; liczy linki zewnętrzne.

    Wynik jest bez duplikatów, w kolejności występowania na stronie,
    bez odnośnika do samej siebie.
    """
    result = LinkSet()
    self_url = normalize_url(page_url)
    seen: set[str] = set()
    external: set[str] = set()

    for href in hrefs:
        url = normalize_url(href, base=page_url)
        if url is None:
            continue
        if not is_internal(url, page_url):
            external.add(url)
            continue
        if url == self_url or url in seen:
            continue
        seen.add(url)

        ext = _extension(url)
        if ext in DOCUMENT_EXTENSIONS:
            result.documents.append(url)
        elif ext not in SKIPPED_EXTENSIONS:
            result.pages.append(url)

    result.external_count = len(external)
    return result
