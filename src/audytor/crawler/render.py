"""Renderowanie strony w Chromium przez Playwright (F3).

Dwa sposoby użycia:

1. Sama migawka (pliki dla reszty zespołu):

       with Renderer() as renderer:
           snapshot = renderer.render("https://example.pl")

2. Żywa strona dla innych modułów (np. axe-core, test fokusu) + migawka z tej samej sesji:

       with Renderer() as renderer:
           with renderer.open("https://example.pl") as opened:
               wyniki_axe = uruchom_axe(opened.page)   # moduł osoby 2
               snapshot = renderer.capture(opened)
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, Response, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from audytor import __version__

from .cookies import CookieBannerResult, handle_cookie_banner
from .links import classify_links, normalize_url
from .robots import USER_AGENT_TOKEN, RobotsCache, RobotsPolicy
from .snapshot import PageSnapshot, add_base_href

PROJECT_URL = "https://github.com/Shuft123/polski-audytor-wcag"

# Przewija stronę ekran po ekranie, żeby załadować obrazki "lazy", potem wraca na górę.
_AUTOSCROLL_JS = """
async (maxHeight) => {
  const doc = document.scrollingElement || document.documentElement;
  const step = Math.max(window.innerHeight, 200);
  const limit = Math.min(doc.scrollHeight, maxHeight);
  for (let y = 0; y < limit; y += step) {
    window.scrollTo(0, y);
    await new Promise(r => setTimeout(r, 120));
  }
  window.scrollTo(0, 0);
}
"""


_PAGE_HEIGHT_JS = """
() => Math.max(
  document.documentElement ? document.documentElement.scrollHeight : 0,
  document.body ? document.body.scrollHeight : 0
)
"""


class RobotsDisallowedError(Exception):
    """Adres zablokowany przez robots.txt."""

    def __init__(self, url: str, policy: RobotsPolicy):
        reason = "robots.txt nieosiągalny" if policy.status == "unreachable" else "zablokowane w robots.txt"
        super().__init__(f"{url}: {reason} ({policy.robots_url})")
        self.url = url
        self.policy = policy


class RenderError(Exception):
    """Nie udało się otworzyć lub wyrenderować strony."""


@dataclass
class RenderOptions:
    viewport_width: int = 1366
    viewport_height: int = 768
    timeout_ms: int = 30_000          # limit na wczytanie strony
    network_idle_ms: int = 5_000      # ile maks. czekać na wyciszenie sieci (nie zawsze następuje)
    settle_ms: int = 1_000            # dodatkowa pauza po renderze (animacje, skrypty)
    scroll: bool = True               # przewijanie dla obrazków "lazy"
    max_scroll_height: int = 20_000   # px; chroni przed stronami "nieskończonymi"
    max_screenshot_height: int = 15_000  # px; dłuższe strony są przycinane
    screenshot_type: str = "png"      # "png" albo "jpeg"
    jpeg_quality: int = 80
    save_mhtml: bool = True
    respect_robots: bool = True
    locale: str = "pl-PL"
    channel: str | None = None        # None = Chromium z Playwrighta; "msedge"/"chrome" = przeglądarka z systemu
    dismiss_cookies: bool = True      # zamykaj baner cookies przyciskiem "odrzuć"/"tylko niezbędne"
    cookie_wait_ms: int = 2_000       # ile czekać na baner, który pojawia się z opóźnieniem


@dataclass
class OpenedPage:
    """Otwarta, wyrenderowana strona. Ważna tylko wewnątrz `with renderer.open(...)`."""

    page: Page
    requested_url: str
    final_url: str
    http_status: int | None
    robots: RobotsPolicy
    render_ms: int
    fetched_at: str
    cookie_banner: CookieBannerResult | None = None   # None = nie sprawdzano (dismiss_cookies=False)
    warnings: list[str] = field(default_factory=list)


class Renderer:
    """Zarządza przeglądarką. Jedna instancja może wyrenderować wiele stron."""

    def __init__(self, options: RenderOptions | None = None, headless: bool = True):
        self.options = options or RenderOptions()
        self.headless = headless
        self.user_agent = ""
        self._playwright = None
        self._browser = None
        self.robots: RobotsCache | None = None

    # --- cykl życia przeglądarki -------------------------------------------------
    def __enter__(self) -> "Renderer":
        if self._browser is None:
            self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def start(self) -> None:
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(
                headless=self.headless, channel=self.options.channel
            )
        except Exception:
            self._playwright.stop()
            self._playwright = None
            raise
        probe = self._browser.new_page()
        default_ua = probe.evaluate("navigator.userAgent")
        probe.close()
        # "HeadlessChrome" bywa blokowane – przedstawiamy się jako Chrome + nazwa projektu.
        self.user_agent = (
            default_ua.replace("HeadlessChrome", "Chrome")
            + f" {USER_AGENT_TOKEN}/{__version__} (+{PROJECT_URL})"
        )
        self.robots = RobotsCache(self.user_agent, enabled=self.options.respect_robots)

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    # --- renderowanie ------------------------------------------------------------
    @contextmanager
    def open(self, url: str) -> Iterator[OpenedPage]:
        """Otwiera i renderuje stronę; zamyka ją po wyjściu z bloku `with`."""
        if self._browser is None or self.robots is None:
            raise RuntimeError("Renderer nie jest uruchomiony – użyj `with Renderer() as r:`")
        normalized = normalize_url(url)
        if normalized is None:
            raise RenderError(f"Nieprawidłowy adres (wymagany http/https): {url!r}")

        policy = self.robots.policy_for(normalized)
        if not policy.can_fetch(normalized):
            raise RobotsDisallowedError(normalized, policy)

        opts = self.options
        context = self._browser.new_context(
            viewport={"width": opts.viewport_width, "height": opts.viewport_height},
            user_agent=self.user_agent,
            locale=opts.locale,
        )
        try:
            page = context.new_page()
            page.set_default_timeout(opts.timeout_ms)
            warnings: list[str] = []
            fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            started = time.monotonic()

            try:
                response: Response | None = page.goto(normalized, wait_until="load", timeout=opts.timeout_ms)
            except PlaywrightTimeoutError:
                # Strona mogła się częściowo wczytać – pracujemy na tym, co jest.
                response = None
                warnings.append(f"Przekroczono limit {opts.timeout_ms} ms na zdarzenie 'load'")
            except PlaywrightError as exc:
                raise RenderError(f"{normalized}: {exc.message.splitlines()[0]}") from exc

            try:
                page.wait_for_load_state("networkidle", timeout=opts.network_idle_ms)
            except PlaywrightTimeoutError:
                warnings.append("Sieć nie ucichła (networkidle) – możliwe doładowywane elementy")

            if opts.scroll:
                try:
                    page.evaluate(_AUTOSCROLL_JS, opts.max_scroll_height)
                except PlaywrightError as exc:
                    warnings.append(f"Przewijanie nie powiodło się: {exc.message.splitlines()[0]}")
            page.wait_for_timeout(opts.settle_ms)

            # Baner cookies obsługujemy PO przewinięciu: część stron pokazuje go z opóźnieniem
            # albo dopiero po przewinięciu (np. bialystok.pl).
            cookie_banner = None
            if opts.dismiss_cookies:
                try:
                    cookie_banner = handle_cookie_banner(
                        page, self._screenshot_kwargs(), wait_for_banner_ms=opts.cookie_wait_ms
                    )
                    warnings.extend(cookie_banner.warnings)
                except PlaywrightError as exc:
                    warnings.append(f"Obsługa banera cookies nie powiodła się: {exc.message.splitlines()[0]}")

            final_url = page.url
            if final_url != normalized and not self.robots.can_fetch(final_url):
                raise RobotsDisallowedError(final_url, self.robots.policy_for(final_url))

            status = response.status if response is not None else None
            if status is not None and status >= 400:
                warnings.append(f"Serwer zwrócił kod HTTP {status}")

            yield OpenedPage(
                page=page,
                requested_url=url,
                final_url=final_url,
                http_status=status,
                robots=self.robots.policy_for(final_url),
                render_ms=int((time.monotonic() - started) * 1000),
                fetched_at=fetched_at,
                cookie_banner=cookie_banner,
                warnings=warnings,
            )
        finally:
            context.close()

    def capture(self, opened: OpenedPage) -> PageSnapshot:
        """Robi migawkę otwartej strony: DOM, zrzut całej strony, MHTML, linki."""
        page = opened.page
        opts = self.options
        warnings = list(opened.warnings)

        dom = add_base_href(page.content(), opened.final_url)
        hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        title = page.title()
        lang = page.evaluate("document.documentElement.getAttribute('lang') || ''")

        screenshot = self._screenshot(page, warnings)

        mhtml = None
        if opts.save_mhtml:
            try:
                cdp = page.context.new_cdp_session(page)
                mhtml = cdp.send("Page.captureSnapshot", {"format": "mhtml"})["data"]
                cdp.detach()
            except PlaywrightError as exc:
                warnings.append(f"Nie udało się zapisać MHTML: {exc.message.splitlines()[0]}")

        links = classify_links(hrefs, opened.final_url)
        allowed = [u for u in links.pages if self.robots.can_fetch(u)]
        allowed_set = set(allowed)
        blocked = [u for u in links.pages if u not in allowed_set]

        return PageSnapshot(
            requested_url=opened.requested_url,
            final_url=opened.final_url,
            http_status=opened.http_status,
            fetched_at=opened.fetched_at,
            title=title,
            lang=lang,
            viewport={"width": opts.viewport_width, "height": opts.viewport_height},
            user_agent=self.user_agent,
            render_ms=opened.render_ms,
            robots=opened.robots.to_dict(),
            links_internal=allowed,
            links_blocked_by_robots=blocked,
            documents=links.documents,
            links_external_count=links.external_count,
            dom_html=dom,
            screenshot=screenshot,
            screenshot_type=opts.screenshot_type,
            mhtml=mhtml,
            cookie_banner=opened.cookie_banner.to_dict() if opened.cookie_banner else {"checked": False},
            cookie_banner_screenshot=opened.cookie_banner.screenshot if opened.cookie_banner else None,
            warnings=warnings,
        )

    def _screenshot_kwargs(self) -> dict:
        kwargs: dict = {"type": self.options.screenshot_type, "animations": "disabled"}
        if self.options.screenshot_type == "jpeg":
            kwargs["quality"] = self.options.jpeg_quality
        return kwargs

    def _screenshot(self, page: Page, warnings: list[str]) -> bytes:
        """Zrzut całej strony; bardzo długie strony są przycinane do `max_screenshot_height`,
        bo Chromium nie potrafi zrobić zrzutu o dowolnej wysokości."""
        opts = self.options
        kwargs: dict = {"full_page": True, **self._screenshot_kwargs()}

        height = page.evaluate(_PAGE_HEIGHT_JS)
        if height > opts.max_screenshot_height:
            warnings.append(
                f"Strona ma {height} px wysokości – zrzut przycięty do {opts.max_screenshot_height} px"
            )
            kwargs["clip"] = {"x": 0, "y": 0, "width": opts.viewport_width,
                              "height": opts.max_screenshot_height}
        try:
            return page.screenshot(**kwargs)
        except PlaywrightError as exc:
            warnings.append(
                f"Zrzut całej strony nie powiódł się ({exc.message.splitlines()[0]}) – zapisano tylko widok okna"
            )
            kwargs.pop("clip", None)
            kwargs["full_page"] = False
            return page.screenshot(**kwargs)

    def render(self, url: str) -> PageSnapshot:
        """Otwiera stronę, robi migawkę i zamyka stronę."""
        try:
            with self.open(url) as opened:
                return self.capture(opened)
        except PlaywrightError as exc:
            raise RenderError(f"{url}: {exc.message.splitlines()[0]}") from exc
