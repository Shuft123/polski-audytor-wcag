"""Wykrywanie deklaracji dostępności na stronie (F17).

Dwa etapy:

1. `find_candidates(html, page_url)` – bez sieci. Przegląda DOM strony głównej
   (np. `dom.html` z migawki crawlera) i ocenia każdy link punktami:
   tekst linku, adres, położenie w stopce, meta tag `deklaracja-dostępności`.
2. `find_declaration(site_url, verify=True)` – z siecią. Pobiera stronę główną,
   wybiera kandydatów, pobiera kilka najlepszych i sprawdza, czy mają identyfikatory
   `a11y-*` z warunków technicznych. Gdy na stronie nie ma żadnego linku, próbuje
   typowych adresów (/deklaracja-dostepnosci itd.). Zawsze respektuje robots.txt.

Wynik to `DeclarationResult` z polem `to_dict()` gotowym do zapisu w JSON.
Pewność (0–1) to heurystyka – wyniki bez weryfikacji traktujemy jako „do weryfikacji”.
"""

from __future__ import annotations

import re
import socket
import ssl
import time
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from audytor import __version__
from audytor.crawler.links import is_internal, normalize_url
from audytor.crawler.robots import STATUS_UNREACHABLE, USER_AGENT_TOKEN, RobotsCache

from .wymagania import META_NAZWY, OBOWIAZKOWE_ID, WSZYSTKIE_ZNANE_ID

USER_AGENT = (
    f"Mozilla/5.0 (compatible; {USER_AGENT_TOKEN}/{__version__}; "
    "+https://github.com/Shuft123/polski-audytor-wcag)"
)

# Typowe adresy deklaracji – sprawdzane tylko, gdy na stronie nie ma żadnego kandydata.
COMMON_PATHS: tuple[str, ...] = (
    "/deklaracja-dostepnosci",
    "/deklaracja-dostepnosci/",
    "/deklaracja-dostepnosci.html",
    "/deklaracja_dostepnosci",
    "/dostepnosc",
    "/dostepnosc-cyfrowa/deklaracja-dostepnosci/",
)

MIN_SCORE = 20          # poniżej tego link nie jest kandydatem
VERIFY_TOP = 3          # ilu najlepszych kandydatów pobieramy przy weryfikacji
MAX_PAGE_BYTES = 3 * 1024 * 1024

# --- metody wykrycia (pole `method` w wyniku) --------------------------------------
METHOD_META = "meta"            # <meta name="deklaracja-dostępności" content="...">
METHOD_LINK = "link"            # link na stronie głównej
METHOD_GUESS = "typowy_adres"   # typowy adres, bez linku na stronie
METHOD_NONE = "brak"

# --- stan wyniku (pole `status`) -------------------------------------------------------
STATUS_VERIFIED = "zweryfikowana"      # strona ma a11y-* albo formułę deklaracji
STATUS_NO_A11Y = "bez_a11y"            # mocny link, strona działa, ale bez a11y-* (np. sklep – PAD)
STATUS_UNVERIFIED = "niezweryfikowana"  # tryb bez sieci (migawka) – tylko link
STATUS_NONE = "brak"

_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}
_FOOTER_HINT = re.compile(r"foot|stopk", re.IGNORECASE)


def normalize_text(text: str) -> str:
    """Małe litery, bez polskich znaków i nadmiarowych spacji („Dostępność” -> „dostepnosc”)."""
    text = text.replace("ł", "l").replace("Ł", "L")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().split())


# --- reguły punktowania -------------------------------------------------------------
# Wzorce działają na tekście po normalize_text (bez polskich znaków).
_TEXT_DECLARATION = re.compile(r"deklaracj\w*\s+(o\s+)?dostepnosc")
_TEXT_EN_STATEMENT = re.compile(r"accessibility\s+(statement|declaration)|declaration\s+of\s+accessibility")
_TEXT_DECLARATION_WORD = re.compile(r"\bdeklaracj")
# „dostępność” jako rzeczownik – NIE „dostępny/dostępna” (np. „kiedy iPhone będzie dostępny”).
_TEXT_ACCESSIBILITY = re.compile(r"\bdostepnosc\w*|\baccessibility\b")
_TEXT_DIGITAL = re.compile(r"dostepnosc\w*\s+cyfrow")
# Strony o dostępności, które NIE są deklaracją cyfrową.
_TEXT_OTHER_ACCESSIBILITY = re.compile(
    r"architektoniczn|niepelnosprawn|komunikacyjn|tlumacz|migow|\bpjm\b|\betr\b|latw\w* (tekst|jezyk)"
    r"|plan dzialan|koordynator|raport"
)
_HREF_DECLARATION = re.compile(r"deklaracj\w*[-_]?(o[-_])?dostepnosc|accessibility[-_]statement")
_HREF_DECLARATION_WORD = re.compile(r"deklaracj")
_HREF_ACCESSIBILITY = re.compile(r"dostepnosc|accessibility|a11y")


@dataclass
class LinkInfo:
    """Link zebrany z DOM wraz z kontekstem."""

    href: str
    text: str = ""          # tekst linku + alt obrazków w środku
    title: str = ""
    aria_label: str = ""
    in_footer: bool = False
    position: int = 0       # kolejność na stronie


@dataclass
class Candidate:
    url: str
    score: int
    reasons: list[str] = field(default_factory=list)
    text: str = ""
    in_footer: bool = False
    internal: bool = True
    occurrences: int = 1
    position: int = 0
    # wypełniane przy weryfikacji
    verified: bool | None = None
    a11y_ids: list[str] = field(default_factory=list)
    http_status: int | None = None
    error: str | None = None

    @property
    def confidence(self) -> float:
        return round(min(self.score, 100) / 100, 2)


@dataclass
class DeclarationResult:
    site_url: str
    found: bool
    declaration_url: str | None
    method: str
    confidence: float
    verified: bool
    a11y_ids: list[str] = field(default_factory=list)
    missing_required_ids: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: str = STATUS_NONE

    def to_dict(self) -> dict:
        data = asdict(self)
        for cand, raw in zip(self.candidates, data["candidates"]):
            raw["confidence"] = cand.confidence
        return data


# --- parser DOM ------------------------------------------------------------------------
class _LinkCollector(HTMLParser):
    """Zbiera linki <a href> z kontekstem (stopka) i meta tag deklaracji.

    Używamy html.parser z biblioteki standardowej, żeby moduł nie miał nowych zależności.
    Stos elementów jest „tolerancyjny”: zamknięcie znacznika zdejmuje ze stosu wszystko
    do pasującego otwarcia, a niedomknięte znaczniki nie psują wyniku.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[LinkInfo] = []
        self.meta_declaration: str | None = None
        self._stack: list[tuple[str, bool]] = []  # (tag, czy ten element to stopka)
        self._current: LinkInfo | None = None
        self._current_depth = 0
        self._skip_depth = 0  # wewnątrz <script>/<style>

    def _in_footer(self) -> bool:
        return any(is_footer for _, is_footer in self._stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            name = normalize_text(a.get("name", ""))
            if name in {normalize_text(n) for n in META_NAZWY} and a.get("content"):
                self.meta_declaration = a["content"].strip()
            return
        if tag == "img" and self._current is not None:
            alt = a.get("alt", "").strip()
            if alt:
                self._current.text += " " + alt
            return
        if tag in _VOID_TAGS:
            return
        if tag in ("script", "style", "noscript", "template"):
            self._skip_depth += 1

        is_footer = (
            tag == "footer"
            or a.get("role", "").lower() == "contentinfo"
            or bool(_FOOTER_HINT.search(a.get("id", "")))
            or bool(_FOOTER_HINT.search(a.get("class", "")))
        )
        self._stack.append((tag, is_footer))

        if tag == "a" and a.get("href"):
            self._current = LinkInfo(
                href=a["href"],
                title=a.get("title", ""),
                aria_label=a.get("aria-label", ""),
                in_footer=self._in_footer(),
                position=len(self.links),
            )
            self._current_depth = len(self._stack)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # <tag /> – traktujemy jak element bez zawartości
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS and self._stack and self._stack[-1][0] == tag:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_TAGS:
            return
        if not any(t == tag for t, _ in self._stack):
            return  # zamknięcie bez otwarcia – ignorujemy
        while self._stack:
            popped, _ = self._stack.pop()
            if self._current is not None and len(self._stack) < self._current_depth:
                self._finish_link()
            if popped in ("script", "style", "noscript", "template"):
                self._skip_depth = max(0, self._skip_depth - 1)
            if popped == tag:
                break

    def handle_data(self, data: str) -> None:
        if self._current is not None and not self._skip_depth:
            self._current.text += data

    def _finish_link(self) -> None:
        assert self._current is not None
        self._current.text = " ".join(self._current.text.split())
        self.links.append(self._current)
        self._current = None

    def close(self) -> None:
        super().close()
        if self._current is not None:
            self._finish_link()


def collect_links(html: str) -> tuple[list[LinkInfo], str | None]:
    """Zwraca linki z DOM i adres z meta tagu deklaracji (albo None)."""
    parser = _LinkCollector()
    parser.feed(html)
    parser.close()
    return parser.links, parser.meta_declaration


# --- punktowanie ----------------------------------------------------------------------
def score_link(link: LinkInfo, url: str, page_url: str) -> tuple[int, list[str]]:
    """Punkty i uzasadnienia dla jednego linku (0 = na pewno nie deklaracja)."""
    label = normalize_text(f"{link.text} {link.aria_label} {link.title}")
    parts = urlsplit(url)
    path = normalize_text(unquote(parts.path + ("?" + parts.query if parts.query else "")))
    score = 0
    reasons: list[str] = []

    if _TEXT_DECLARATION.search(label) or _TEXT_EN_STATEMENT.search(label):
        score += 60
        reasons.append("tekst: „deklaracja dostępności”")
    elif _TEXT_DECLARATION_WORD.search(label) and _TEXT_ACCESSIBILITY.search(label):
        score += 50
        reasons.append("tekst: „deklaracja” + „dostępność”")
    elif _TEXT_DIGITAL.search(label):
        score += 25
        reasons.append("tekst: „dostępność cyfrowa”")
    elif _TEXT_ACCESSIBILITY.search(label):
        score += 20
        reasons.append("tekst: „dostępność”")

    if _HREF_DECLARATION.search(path):
        score += 30
        reasons.append("adres: deklaracja-dostepnosci")
    elif _HREF_DECLARATION_WORD.search(path) and score > 0:
        # samo „deklaracja” w adresie liczy się tylko przy pasującym tekście
        # (np. bialystok.pl: /cms/deklaracja) – inaczej łapalibyśmy deklaracje podatkowe
        score += 15
        reasons.append("adres: deklaracja")
    elif _HREF_ACCESSIBILITY.search(path):
        score += 10
        reasons.append("adres: dostepnosc")

    if score == 0:
        return 0, []

    if _TEXT_OTHER_ACCESSIBILITY.search(label) and not _TEXT_DECLARATION_WORD.search(label):
        score -= 15
        reasons.append("inna strona o dostępności (architektoniczna, PJM, ETR…)")

    if link.in_footer:
        score += 15
        reasons.append("w stopce")

    if not is_internal(url, page_url):
        # deklaracja bywa w BIP na innej domenie – nie odrzucamy, tylko obniżamy
        score -= 5
        reasons.append("inna domena")

    return max(score, 0), reasons


def find_candidates(html: str, page_url: str) -> tuple[list[Candidate], str | None]:
    """Kandydaci na deklarację (malejąco wg punktów) i adres z meta tagu (jeśli jest).

    Nie używa sieci – działa na zapisanym DOM (np. dom.html z migawki).
    """
    links, meta = collect_links(html)
    by_url: dict[str, Candidate] = {}
    for link in links:
        url = normalize_url(link.href, base=page_url)
        if url is None or url == normalize_url(page_url):
            continue
        score, reasons = score_link(link, url, page_url)
        if score < MIN_SCORE:
            continue
        existing = by_url.get(url)
        if existing is None:
            by_url[url] = Candidate(
                url=url, score=score, reasons=reasons, text=link.text[:120],
                in_footer=link.in_footer, internal=is_internal(url, page_url),
                position=link.position,
            )
        else:
            existing.occurrences += 1
            if score > existing.score:
                existing.score, existing.reasons = score, reasons
                existing.text, existing.in_footer = link.text[:120], link.in_footer

    meta_url = normalize_url(meta, base=page_url) if meta else None
    if meta_url:
        cand = by_url.get(meta_url)
        if cand is None:
            cand = by_url[meta_url] = Candidate(
                url=meta_url, score=0, internal=is_internal(meta_url, page_url), position=-1,
            )
        cand.score = max(cand.score, 0) + 100
        cand.reasons.insert(0, "meta tag deklaracja-dostępności")

    # Najwyżej punkty; przy remisie wcześniej na stronie (meta tag ma position=-1).
    return sorted(by_url.values(), key=lambda c: (-c.score, c.position)), meta_url


# --- analiza strony kandydata ---------------------------------------------------------
_ID_ATTR = re.compile(r"""\bid\s*=\s*["']?\s*(a11y-[a-z0-9-]+)""", re.IGNORECASE)


def a11y_ids_in(html: str) -> list[str]:
    """Znane identyfikatory a11y-* występujące w kodzie strony (bez duplikatów, posortowane)."""
    found = {m.group(1).lower() for m in _ID_ATTR.finditer(html)}
    return sorted(found & WSZYSTKIE_ZNANE_ID)


def looks_like_declaration(html: str) -> bool:
    """Słabszy test dla deklaracji bez identyfikatorów: tytuł + formuła wstępu."""
    text = normalize_text(re.sub(r"<[^>]+>", " ", html))
    return "deklaracja dostepnosci" in text and "zobowiazuje sie zapewnic dostepnosc" in text


# --- sieć -------------------------------------------------------------------------------
Fetcher = Callable[[str], tuple[int | None, str, str]]  # url -> (status, final_url, html)

# Kody, przy których serwer zwykle odrzuca „nie-przeglądarkę” (ochrona przed botami).
_BOT_BLOCK_CODES = {401, 403, 429, 503}
FEW_LINKS = 5  # mniej linków na stronie głównej = pewnie strona budowana w JS


class BlockedError(Exception):
    """Strony nie wolno pobrać (robots.txt zabrania albo jest nieosiągalny)."""


def describe_error(error: object) -> str:
    """Czytelny opis błędu sieci (wyjątek albo tekst błędu)."""
    reason = getattr(error, "reason", error)
    text = str(reason)
    if isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in text:
        return ("błąd certyfikatu SSL – serwer ma niepełny łańcuch certyfikatów "
                "(pomaga pakiet truststore: pip install truststore)")
    if isinstance(reason, socket.gaierror) or "getaddrinfo" in text or "Name or service not known" in text:
        return "domena nie istnieje albo brak internetu (DNS)"
    if isinstance(reason, TimeoutError) or "timed out" in text:
        return "przekroczony czas odpowiedzi"
    return text


def _is_ssl_error(error: object) -> bool:
    reason = getattr(error, "reason", error)
    return isinstance(reason, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(reason)


def fetch_html(url: str, timeout: float = 15.0) -> tuple[int | None, str, str]:
    """Pobiera stronę bez renderowania JS. Zwraca (status HTTP, adres końcowy, HTML)."""
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "pl-PL,pl;q=0.9",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_PAGE_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
            return response.status, response.geturl(), raw.decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, url, ""


class BrowserFetcher:
    """Pobieranie przez Chromium (moduł crawlera) – dla stron z JS, ochroną przed botami
    albo certyfikatem, którego Python nie umie sprawdzić. Przeglądarka startuje dopiero
    przy pierwszym użyciu; po pracy wywołaj close().

    robots.txt sprawdza _PoliteFetcher przed wywołaniem, więc tu go nie powtarzamy.
    """

    def __init__(self) -> None:
        self._renderer = None

    @staticmethod
    def available() -> bool:
        try:
            import playwright  # noqa: F401
        except ImportError:
            return False
        return True

    def __call__(self, url: str) -> tuple[int | None, str, str]:
        from audytor.crawler import Renderer, RenderOptions

        if self._renderer is None:
            self._renderer = Renderer(RenderOptions(save_mhtml=False, scroll=False, respect_robots=False))
            self._renderer.start()
        try:
            with self._renderer.open(url) as opened:
                return opened.http_status, opened.final_url, opened.page.content()
        except Exception as exc:  # błędy Playwrighta mają różne typy – ujednolicamy do OSError
            raise OSError(f"przeglądarka: {exc}") from exc

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None


class _FallbackFetcher:
    """Najpierw zwykłe pobranie; przy błędzie SSL albo blokadzie botów – przeglądarka."""

    def __init__(self, primary: Fetcher, browser: Fetcher | None):
        self.primary = primary
        self.browser = browser
        self.notes: list[str] = []

    def __call__(self, url: str) -> tuple[int | None, str, str]:
        try:
            status, final_url, html = self.primary(url)
        except (urllib.error.URLError, OSError) as exc:
            if self.browser is None or not _is_ssl_error(exc):
                raise
            self.notes.append(f"{url}: {BROWSER_NOTE} ({describe_error(exc)})")
            return self.browser(url)
        if status in _BOT_BLOCK_CODES and self.browser is not None:
            self.notes.append(f"{url}: {BROWSER_NOTE} (serwer zwrócił HTTP {status} dla zwykłego zapytania)")
            return self.browser(url)
        return status, final_url, html


class _PoliteFetcher:
    """Opakowanie pobierania: robots.txt + pauza między zapytaniami do tej samej witryny."""

    def __init__(self, fetch: Fetcher, robots: RobotsCache | None, delay: float):
        self.fetch = fetch
        self.robots = robots
        self.delay = delay
        self._last = 0.0

    def check_robots(self, url: str) -> None:
        if self.robots is None:
            return
        policy = self.robots.policy_for(url)
        if policy.can_fetch(url):
            return
        if policy.status == STATUS_UNREACHABLE:
            raise BlockedError(
                f"robots.txt nieosiągalny – {describe_error(policy.error)}; "
                f"zgodnie z RFC 9309 nie pobieramy strony ({policy.robots_url})"
            )
        raise BlockedError(f"robots.txt zabrania pobrania {url} botowi {USER_AGENT_TOKEN} ({policy.robots_url})")

    def __call__(self, url: str) -> tuple[int | None, str, str]:
        self.check_robots(url)
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        try:
            return self.fetch(url)
        finally:
            self._last = time.monotonic()


def _verify(candidate: Candidate, fetch: Fetcher) -> None:
    try:
        status, final_url, html = fetch(candidate.url)
    except BlockedError as exc:
        candidate.verified, candidate.error = False, str(exc)
        return
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        candidate.verified, candidate.error = False, f"błąd pobierania: {describe_error(exc)}"
        return
    candidate.http_status = status
    if status is None or status >= 400 or not html:
        candidate.verified, candidate.error = False, f"HTTP {status}"
        return
    if final_url and normalize_url(final_url):
        candidate.url = normalize_url(final_url) or candidate.url
    candidate.a11y_ids = a11y_ids_in(html)
    candidate.verified = bool(candidate.a11y_ids) or looks_like_declaration(html)
    if candidate.a11y_ids:
        candidate.reasons.append(f"strona ma {len(candidate.a11y_ids)} identyfikatorów a11y-*")
    elif candidate.verified:
        candidate.reasons.append("strona wygląda na deklarację, ale bez identyfikatorów a11y-*")


NO_A11Y_MIN_SCORE = 60         # silny link (tekst „deklaracja dostępności”) do strony bez a11y-*
NO_A11Y_MIN_SCORE_FOOTER = 45  # albo „Dostępność …” w stopce (sklepy: „Dostępność usług”)
NOT_FOUND_WARNING = "Nie znaleziono linku do deklaracji na stronie głównej ani pod typowymi adresami."
BROWSER_NOTE = "pobrano przeglądarką"

NO_A11Y_WARNING = (
    "Strona pod linkiem działa, ale nie ma identyfikatorów a11y-* ani formuły deklaracji. "
    "U podmiotu prywatnego (sklep) to zwykle informacja o dostępności wg ustawy z 2024 r. (PAD); "
    "u podmiotu publicznego – deklaracja niezgodna z warunkami technicznymi."
)


def _result_from(site_url: str, cands: list[Candidate], meta_url: str | None,
                 verified_mode: bool, warnings: list[str], method_override: str | None = None) -> DeclarationResult:
    if not cands:
        if verified_mode:
            warnings.append(NOT_FOUND_WARNING)
        return DeclarationResult(site_url, False, None, METHOD_NONE, 0.0, False,
                                 candidates=[], warnings=warnings, status=STATUS_NONE)
    if verified_mode:
        # najpierw zweryfikowani (najwięcej a11y-*), potem reszta wg punktów
        ranked = sorted(cands, key=lambda c: (not c.verified, -len(c.a11y_ids), -c.score, c.position))
    else:
        ranked = cands
    best = ranked[0]
    method = method_override or (METHOD_META if meta_url and best.url == meta_url else METHOD_LINK)
    missing = [i for i in OBOWIAZKOWE_ID if i not in best.a11y_ids] if best.verified else []

    if not verified_mode:
        found, status, confidence = True, STATUS_UNVERIFIED, best.confidence
    elif best.verified:
        found, status = True, STATUS_VERIFIED
        confidence = 0.95 if best.a11y_ids else 0.8
        if not best.a11y_ids:
            warnings.append("Deklaracja bez identyfikatorów a11y-* (niezgodna z warunkami technicznymi).")
    elif (best.http_status is not None and best.http_status < 400
          and (best.score >= NO_A11Y_MIN_SCORE or (best.in_footer and best.score >= NO_A11Y_MIN_SCORE_FOOTER))):
        found, status, confidence = True, STATUS_NO_A11Y, 0.6
        warnings.append(NO_A11Y_WARNING)
    else:
        found, status, confidence = False, STATUS_NONE, min(best.confidence, 0.4)
        reason = best.error or "strona pod linkiem nie wygląda na deklarację"
        warnings.append(f"Najlepszy kandydat {best.url} odrzucony: {reason}.")

    return DeclarationResult(
        site_url=site_url, found=found, declaration_url=best.url, method=method,
        confidence=confidence, verified=status == STATUS_VERIFIED,
        a11y_ids=best.a11y_ids, missing_required_ids=missing,
        candidates=ranked, warnings=warnings, status=status,
    )


def main_reason(result: DeclarationResult) -> str | None:
    """Najważniejsze ostrzeżenie do wyświetlenia (pomija notatki o użyciu przeglądarki)."""
    real = [w for w in result.warnings if BROWSER_NOTE not in w]
    return (real or result.warnings or [None])[-1]


def find_in_html(html: str, page_url: str) -> DeclarationResult:
    """Wynik tylko z DOM strony głównej (bez sieci) – np. dla migawki crawlera."""
    cands, meta_url = find_candidates(html, page_url)
    return _result_from(page_url, cands, meta_url, verified_mode=False, warnings=[])


def find_declaration(
    site_url: str,
    *,
    html: str | None = None,
    verify: bool = True,
    guess_paths: bool = True,
    respect_robots: bool = True,
    delay: float = 1.0,
    fetch: Fetcher = fetch_html,
    browser: Fetcher | None = None,
) -> DeclarationResult:
    """Pełne wyszukiwanie deklaracji dla witryny.

    html – gotowy DOM strony głównej (np. z Renderer/migawki). Gdy None, strona jest
           pobierana bez renderowania JS (wystarcza dla większości stron urzędów).
    verify – pobierz najlepszych kandydatów i sprawdź identyfikatory a11y-*.
    fetch – funkcja pobierająca (podmieniana w testach).
    browser – zapasowe pobieranie przez przeglądarkę (np. BrowserFetcher()): używane przy
              błędzie SSL, blokadzie botów (403/429/503) i stronie głównej z bardzo małą liczbą linków.
    """
    warnings: list[str] = []
    robots = RobotsCache(USER_AGENT) if respect_robots else None
    fallback = _FallbackFetcher(fetch, browser)
    polite = _PoliteFetcher(fallback, robots, delay)

    def fail(message: str) -> DeclarationResult:
        return DeclarationResult(page_url, False, None, METHOD_NONE, 0.0, False,
                                 warnings=[*fallback.notes, message], status=STATUS_NONE)

    page_url = normalize_url(site_url) or site_url
    if html is None:
        try:
            status, final_url, html = polite(page_url)
        except BlockedError as exc:
            return fail(str(exc))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            return fail(f"Nie udało się pobrać strony głównej: {describe_error(exc)}")
        if status is None or status >= 400:
            warnings.append(f"Strona główna zwróciła HTTP {status}.")
        page_url = normalize_url(final_url) or page_url
        if html and len(collect_links(html)[0]) < FEW_LINKS:
            if browser is not None:
                try:
                    _, final_url, html = browser(page_url)
                    page_url = normalize_url(final_url) or page_url
                    fallback.notes.append(
                        f"{page_url}: mało linków w HTML – strona główna wyrenderowana w przeglądarce")
                except OSError as exc:
                    warnings.append(f"Renderowanie strony głównej nieudane: {exc}")
            else:
                warnings.append("Mało linków w HTML – strona może wymagać renderowania JS (zainstaluj Playwright).")

    cands, meta_url = find_candidates(html or "", page_url)
    if not verify:
        return _result_from(page_url, cands, meta_url, verified_mode=False,
                            warnings=[*fallback.notes, *warnings])

    for cand in cands[:VERIFY_TOP]:
        _verify(cand, polite)

    method_override = None
    if guess_paths and not any(c.verified for c in cands[:VERIFY_TOP]):
        for path in COMMON_PATHS:
            url = normalize_url(path, base=page_url)
            if url is None or any(c.url == url for c in cands):
                continue
            guess = Candidate(url=url, score=MIN_SCORE, reasons=["typowy adres deklaracji"], position=10_000)
            _verify(guess, polite)
            if guess.verified:
                cands.insert(0, guess)
                method_override = METHOD_GUESS
                warnings.append("Deklaracja znaleziona pod typowym adresem, ale brak do niej linku "
                                "na stronie głównej (warunki techniczne: link ma być łatwo dostępny).")
                break

    return _result_from(page_url, cands, meta_url, verified_mode=True,
                        warnings=[*fallback.notes, *warnings], method_override=method_override)
