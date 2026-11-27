"""Crawling wielu podstron jednej witryny (F1 v1, F2 – sprint 2).

Od strony startowej przechodzimy wszerz (BFS) po linkach wewnętrznych:
- tylko ta sama witryna (`www.` bez znaczenia, poddomeny to inne witryny – jak w links.is_internal),
- limit głębokości (`max_depth`: 0 = tylko strona startowa, 1 = + linki ze startowej, …),
- limit liczby stron (`max_pages`, łącznie ze startową) i opcjonalnie limit czasu,
- deduplikacja: adres znormalizowany (bez #, bez parametrów śledzących utm_*/fbclid…), a po wczytaniu
  także adres końcowy – dwa linki przekierowujące w to samo miejsce dają jedną stronę,
- robots.txt dla KAŻDEJ podstrony (sprawdza Renderer.open; zablokowane linki nawet nie trafiają do kolejki),
- limit tempa na witrynę: pauza `delay_s` albo Crawl-delay z robots.txt, jeśli większy (F2).

Użycie:

    with Renderer() as renderer:
        wynik = SiteCrawler(renderer, CrawlOptions(max_depth=2, max_pages=20)).crawl(
            "https://www.wasilkow.pl/", out_dir=Path("wyniki/wasilkow-pl"))
    wynik.page_urls()        # sprawdzone podstrony – np. parametry["podstrony"] skanu
    wynik.save(folder)       # crawl.json (format: docs/kontrakt-danych.md, sekcja 1.7)

Hak `on_page(opened, strona)` dostaje otwartą stronę w tej samej sesji przeglądarki – inne moduły
(axe, fokus) mogą działać podczas crawlowania, bez ponownego renderowania.
"""

from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .links import is_internal, normalize_url, strip_tracking
from .render import OpenedPage, PageLinks, Renderer, RenderError, RobotsDisallowedError
from .snapshot import save_snapshot, slug_for_url

CRAWL_FILE = "crawl.json"
CRAWL_SCHEMA_VERSION = "1.0"
MAX_PAGES_LIMIT = 500          # twardy limit – większe witryny to zadanie kolejki (F4, sprint 3)
MAX_DEPTH_LIMIT = 10

# Status strony w wyniku crawlowania
OK = "ok"                      # wczytana (także z kodem HTTP >= 400 – wtedy jej linków nie śledzimy)
BLAD = "blad"                  # nie udało się wczytać (timeout, brak połączenia, plik zamiast strony…)
POMINIETA = "pominieta"        # świadomie pominięta (robots.txt, przekierowanie poza witrynę, duplikat)

# Dlaczego crawlowanie się skończyło
KONIEC_KOLEJKI = "kolejka_pusta"
KONIEC_LIMIT_STRON = "limit_stron"
KONIEC_LIMIT_CZASU = "limit_czasu"
KONIEC_START = "strona_startowa_niedostepna"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def crawl_key(url: str) -> str:
    """Klucz deduplikacji: adres znormalizowany, bez parametrów śledzących."""
    return strip_tracking(normalize_url(url) or url)


@dataclass
class CrawlOptions:
    max_depth: int = 2
    max_pages: int = 20
    delay_s: float = 1.0                  # pauza między stronami tej samej witryny
    time_budget_s: float | None = None    # None = bez limitu czasu
    save_snapshots: bool = True           # False = tylko odkrywanie adresów (bez zrzutów, szybciej)
    follow_error_pages: bool = False      # czy śledzić linki ze stron z kodem HTTP >= 400

    def __post_init__(self) -> None:
        if not 0 <= self.max_depth <= MAX_DEPTH_LIMIT:
            raise ValueError(f"max_depth musi być w zakresie 0–{MAX_DEPTH_LIMIT}")
        if not 1 <= self.max_pages <= MAX_PAGES_LIMIT:
            raise ValueError(f"max_pages musi być w zakresie 1–{MAX_PAGES_LIMIT}")
        if self.delay_s < 0:
            raise ValueError("delay_s nie może być ujemne")


@dataclass
class CrawledPage:
    """Jedna odwiedzona (albo świadomie pominięta) strona."""

    url: str                          # adres z kolejki (znormalizowany)
    depth: int
    found_on: str | None              # strona, na której znaleziono link (None = startowa)
    status: str                       # ok | blad | pominieta
    final_url: str | None = None      # adres po przekierowaniach
    http_status: int | None = None
    title: str | None = None
    snapshot: str | None = None       # nazwa folderu migawki (gdy save_snapshots)
    new_links: int = 0                # ile nowych adresów ta strona dodała do kolejki
    render_ms: int | None = None
    reason: str | None = None         # powód błędu / pominięcia
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CrawlResult:
    start_url: str
    options: CrawlOptions
    started_at: str
    finished_at: str | None = None
    stop_reason: str | None = None
    pages: list[CrawledPage] = field(default_factory=list)
    not_visited: list[dict] = field(default_factory=list)       # {url, depth, reason} – ponad limit
    blocked_by_robots: list[str] = field(default_factory=list)  # linki wewnętrzne zablokowane w robots.txt
    documents: list[str] = field(default_factory=list)          # linki do PDF/DOCX… z całej witryny

    def page_urls(self) -> list[str]:
        """Adresy końcowe sprawdzonych stron (status ok, HTTP < 400), w kolejności odwiedzin."""
        return [p.final_url for p in self.pages
                if p.status == OK and p.final_url and (p.http_status or 200) < 400]

    def summary(self) -> dict:
        def ile(status: str) -> int:
            return sum(1 for p in self.pages if p.status == status)

        return {
            "ok": ile(OK),
            "blad": ile(BLAD),
            "pominieta": ile(POMINIETA),
            "nie_odwiedzone": len(self.not_visited),
            "zablokowane_robots": len(self.blocked_by_robots),
            "dokumenty": len(self.documents),
            "max_glebokosc": max((p.depth for p in self.pages if p.status == OK), default=0),
        }

    def to_dict(self) -> dict:
        return {
            "schema_version": CRAWL_SCHEMA_VERSION,
            "start_url": self.start_url,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "stop_reason": self.stop_reason,
            "options": asdict(self.options),
            "summary": self.summary(),
            "pages": [p.to_dict() for p in self.pages],
            "not_visited": self.not_visited,
            "blocked_by_robots": self.blocked_by_robots,
            "documents": self.documents,
        }

    def save(self, folder: str | Path) -> Path:
        path = Path(folder) / CRAWL_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path


def load_crawl(folder: str | Path) -> dict:
    """Wczytuje crawl.json (pomocnicze dla innych modułów)."""
    return json.loads((Path(folder) / CRAWL_FILE).read_text(encoding="utf-8"))


class RateLimiter:
    """Limit tempa zapytań na witrynę (F2): między stronami tego samego hosta czeka `delay_s`
    albo Crawl-delay z robots.txt, jeśli jest większy. Zegar i usypianie można podmienić w testach."""

    def __init__(
        self,
        delay_s: float,
        crawl_delay: Callable[[str], float | None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.delay_s = max(delay_s, 0.0)
        self._crawl_delay = crawl_delay
        self._clock = clock
        self._sleep = sleep
        self._last: dict[str, float] = {}

    @staticmethod
    def _host(url: str) -> str:
        return (urlsplit(url).hostname or "").removeprefix("www.")

    def wait_time(self, url: str) -> float:
        last = self._last.get(self._host(url))
        if last is None:
            return 0.0
        delay = self.delay_s
        if self._crawl_delay is not None:
            delay = max(delay, self._crawl_delay(url) or 0.0)
        return max(delay - (self._clock() - last), 0.0)

    def wait(self, url: str) -> float:
        pause = self.wait_time(url)
        if pause > 0:
            self._sleep(pause)
        return pause

    def visited(self, url: str) -> None:
        self._last[self._host(url)] = self._clock()


class SiteCrawler:
    """Przechodzi witrynę od strony startowej (BFS) z limitami głębokości, liczby stron i tempa."""

    def __init__(
        self,
        renderer: Renderer,
        options: CrawlOptions | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.renderer = renderer
        self.options = options or CrawlOptions()
        self._clock = clock
        robots = renderer.robots
        self.limiter = RateLimiter(
            self.options.delay_s,
            crawl_delay=(lambda u: robots.policy_for(u).crawl_delay()) if robots else None,
            clock=clock,
            sleep=sleep,
        )

    def crawl(
        self,
        start_url: str,
        out_dir: str | Path | None = None,
        on_page: Callable[[OpenedPage, CrawledPage], None] | None = None,
        on_result: Callable[[CrawledPage], None] | None = None,
    ) -> CrawlResult:
        """Crawluje witrynę. `out_dir` – folder na migawki i crawl.json (wymagany przy save_snapshots).

        `on_page(opened, strona)` – wywoływany dla każdej wczytanej strony, gdy jest jeszcze otwarta;
        błąd w haku jest zapisywany w `warnings` strony i nie przerywa crawlowania.
        `on_result(strona)` – wywoływany po każdej stronie (np. do wypisywania postępu).
        """
        opts = self.options
        start = normalize_url(start_url)
        if start is None:
            raise ValueError(f"Nieprawidłowy adres (wymagany http/https): {start_url!r}")
        start = strip_tracking(start)
        if opts.save_snapshots and out_dir is None:
            raise ValueError("save_snapshots wymaga out_dir")
        out = Path(out_dir) if out_dir is not None else None

        result = CrawlResult(start_url=start, options=opts, started_at=_now_iso())
        queue: deque[tuple[str, int, str | None]] = deque([(start, 0, None)])
        seen = {crawl_key(start)}            # adresy już w kolejce albo odwiedzone
        blocked: dict[str, None] = {}        # zbiór z zachowaniem kolejności
        documents: dict[str, None] = {}
        used_names: set[str] = set()
        visited_finals: set[str] = set()     # adresy końcowe stron już zapisanych jako „ok”
        began = self._clock()
        visited = 0

        def finish(page: CrawledPage) -> None:
            result.pages.append(page)
            if on_result is not None:
                on_result(page)

        while queue:
            if visited >= opts.max_pages:
                result.stop_reason = KONIEC_LIMIT_STRON
                break
            if opts.time_budget_s is not None and self._clock() - began > opts.time_budget_s:
                result.stop_reason = KONIEC_LIMIT_CZASU
                break

            url, depth, parent = queue.popleft()
            page = CrawledPage(url=url, depth=depth, found_on=parent, status=BLAD)

            # robots.txt sprawdzamy przed pauzą – do zablokowanej strony nie wysyłamy zapytania.
            if self.renderer.robots is not None and not self.renderer.robots.can_fetch(url):
                policy = self.renderer.robots.policy_for(url)
                page.status = POMINIETA
                page.reason = ("robots.txt nieosiągalny" if policy.status == "unreachable"
                               else "zablokowane w robots.txt")
                finish(page)
                if depth == 0:
                    result.stop_reason = KONIEC_START
                    break
                continue

            self.limiter.wait(url)
            visited += 1
            try:
                with self.renderer.open(url) as opened:
                    links = self._handle_page(opened, page, start, out, used_names, visited_finals, on_page)
                    if links is not None:
                        for u in links.blocked_by_robots:
                            blocked.setdefault(u, None)
                        for u in links.documents:
                            documents.setdefault(u, None)
                        follow = (page.http_status or 200) < 400 or opts.follow_error_pages
                        if follow and depth < opts.max_depth:
                            for link in links.internal:
                                link = strip_tracking(link)
                                key = crawl_key(link)
                                if key in seen or not is_internal(link, start):
                                    continue
                                seen.add(key)
                                queue.append((link, depth + 1, page.final_url))
                                page.new_links += 1
                        # adres końcowy też jest „widziany” – link do niego nie wróci do kolejki
                        if page.final_url:
                            seen.add(crawl_key(page.final_url))
            except RobotsDisallowedError as exc:     # np. przekierowanie na adres zablokowany w robots.txt
                page.status = POMINIETA
                page.reason = str(exc)
            except RenderError as exc:
                page.status = BLAD
                page.reason = str(exc)
            except Exception as exc:  # noqa: BLE001 – jedna zepsuta strona nie przerywa crawlowania
                page.status = BLAD
                page.reason = f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"
            finally:
                self.limiter.visited(url)

            finish(page)
            if depth == 0 and page.status != OK:
                result.stop_reason = KONIEC_START
                break
        else:
            result.stop_reason = KONIEC_KOLEJKI

        if result.stop_reason in (KONIEC_LIMIT_STRON, KONIEC_LIMIT_CZASU):
            reason = "limit stron" if result.stop_reason == KONIEC_LIMIT_STRON else "limit czasu"
            result.not_visited = [{"url": u, "depth": d, "reason": reason} for u, d, _ in queue]

        visited_ok = {crawl_key(p.final_url) for p in result.pages if p.status == OK and p.final_url}
        result.blocked_by_robots = list(blocked)
        result.documents = list(documents)
        # link zablokowany w robots.txt nie może jednocześnie być stroną odwiedzoną
        result.blocked_by_robots = [u for u in result.blocked_by_robots if crawl_key(u) not in visited_ok]
        result.finished_at = _now_iso()
        if out is not None:
            result.save(out)
        return result

    # --- pomocnicze ---------------------------------------------------------------------------
    def _handle_page(self, opened: OpenedPage, page: CrawledPage, start: str, out: Path | None,
                     used_names: set[str], visited_finals: set[str], on_page) -> PageLinks | None:
        """Uzupełnia `page`; zwraca linki strony albo None, gdy strona została pominięta."""
        final = strip_tracking(normalize_url(opened.final_url) or opened.final_url)
        page.final_url = final
        page.http_status = opened.http_status
        page.render_ms = opened.render_ms
        page.warnings = list(opened.warnings)

        if not is_internal(final, start):
            page.status = POMINIETA
            page.reason = f"przekierowanie poza witrynę: {final}"
            return None
        if crawl_key(final) in visited_finals:   # np. /stary-kontakt -> /kontakt, już odwiedzony
            page.status = POMINIETA
            page.reason = f"ta sama strona co {final} (przekierowanie)"
            return None
        visited_finals.add(crawl_key(final))

        page.status = OK
        try:
            page.title = opened.page.title()
        except Exception:  # noqa: BLE001 – tytuł nie jest konieczny
            page.title = None

        if self.options.save_snapshots and out is not None:
            snapshot = self.renderer.capture(opened)
            name = _unique_name(slug_for_url(final), used_names)
            save_snapshot(snapshot, out, name=name)
            page.snapshot = name
            page.warnings = list(snapshot.warnings)
            links = PageLinks(snapshot.links_internal, snapshot.links_blocked_by_robots,
                              snapshot.documents, snapshot.links_external_count)
        else:
            links = self.renderer.page_links(opened)

        if on_page is not None:
            try:
                on_page(opened, page)
            except Exception as exc:  # noqa: BLE001 – błąd w haku innego modułu nie przerywa crawlowania
                page.warnings.append(f"on_page: {type(exc).__name__}: {exc}")
        return links


def _unique_name(base: str, used: set[str]) -> str:
    name, n = base, 2
    while name in used:
        name = f"{base[:56]}-{n}"
        n += 1
    used.add(name)
    return name
