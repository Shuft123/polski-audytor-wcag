"""Uruchamianie crawlera z wiersza poleceń.

Przykłady:
    python -m audytor.crawler https://pb.edu.pl
    python -m audytor.crawler https://pb.edu.pl https://www.gov.pl --out tests/data/snapshots
    python -m audytor.crawler --urls-file strony.txt --delay 2
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from .links import normalize_url
from .render import Renderer, RenderError, RenderOptions, RobotsDisallowedError
from .snapshot import save_snapshot

DEFAULT_OUT = Path("tests") / "data" / "snapshots"


def _viewport(value: str) -> tuple[int, int]:
    try:
        width, height = (int(v) for v in value.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError("format: SZEROKOŚĆxWYSOKOŚĆ, np. 1366x768") from None
    if width < 200 or height < 200:
        raise argparse.ArgumentTypeError("minimalny rozmiar okna to 200x200")
    return width, height


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m audytor.crawler",
        description="Renderuje strony (Playwright), zapisuje DOM, zrzut ekranu, MHTML "
        "i linki wewnętrzne (1 poziom) z kontrolą robots.txt.",
    )
    parser.add_argument("urls", nargs="*", metavar="URL", help="adresy stron do zapisania")
    parser.add_argument("--urls-file", type=Path, help="plik z adresami, jeden w linii (# = komentarz)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"folder wyjściowy (domyślnie {DEFAULT_OUT})")
    parser.add_argument("--name", help="nazwa folderu migawki (tylko przy jednym adresie)")
    parser.add_argument("--delay", type=float, default=1.0, help="pauza między stronami w sekundach (domyślnie 1)")
    parser.add_argument("--timeout", type=float, default=30.0, help="limit wczytania strony w sekundach (domyślnie 30)")
    parser.add_argument("--viewport", type=_viewport, default=(1366, 768), help="rozmiar okna, np. 1366x768")
    parser.add_argument("--max-height", type=int, default=15000,
                        help="maks. wysokość zrzutu w px; dłuższe strony są przycinane (domyślnie 15000)")
    parser.add_argument("--jpeg", action="store_true", help="zrzut jako JPEG (mniejszy plik) zamiast PNG")
    parser.add_argument("--no-mhtml", action="store_true", help="nie zapisuj kopii MHTML")
    parser.add_argument("--no-scroll", action="store_true", help="nie przewijaj strony przed zrzutem")
    parser.add_argument("--ignore-robots", action="store_true", help="NIE sprawdzaj robots.txt (tylko do testów własnych stron)")
    parser.add_argument("--keep-cookie-banner", action="store_true",
                        help="nie zamykaj banera cookies (domyślnie zamykany przyciskiem odrzucenia)")
    parser.add_argument("--headed", action="store_true", help="pokaż okno przeglądarki")
    parser.add_argument("--channel", choices=["msedge", "chrome"],
                        help="użyj przeglądarki zainstalowanej w systemie zamiast Chromium z Playwrighta")
    return parser


def _read_urls(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[str]:
    urls = list(args.urls)
    if args.urls_file:
        try:
            lines = args.urls_file.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            parser.error(f"nie można odczytać {args.urls_file}: {exc}")
        urls += [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    if not urls:
        parser.error("podaj co najmniej jeden adres URL lub --urls-file")
    bad = [u for u in urls if normalize_url(u) is None]
    if bad:
        parser.error("nieprawidłowe adresy (wymagany http:// lub https://): " + ", ".join(bad))
    if args.name and len(urls) > 1:
        parser.error("--name można użyć tylko z jednym adresem")
    return urls


def _banner_summary(info: dict) -> str:
    if not info.get("checked"):
        return "nie sprawdzano"
    if not info.get("detected"):
        return "brak"
    if info.get("dismissed"):
        return f"zamknięty („{info.get('button_text')}”)"
    return "NIE zamknięty (patrz uwagi)"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    urls = _read_urls(args, parser)

    options = RenderOptions(
        viewport_width=args.viewport[0],
        viewport_height=args.viewport[1],
        timeout_ms=int(args.timeout * 1000),
        scroll=not args.no_scroll,
        max_screenshot_height=args.max_height,
        screenshot_type="jpeg" if args.jpeg else "png",
        save_mhtml=not args.no_mhtml,
        respect_robots=not args.ignore_robots,
        channel=args.channel,
        dismiss_cookies=not args.keep_cookie_banner,
    )

    failures = 0
    last_visit: dict[str, float] = {}
    try:
        renderer = Renderer(options, headless=not args.headed)
        renderer.start()
    except Exception as exc:
        print(f"Nie udało się uruchomić przeglądarki: {str(exc).splitlines()[0]}", file=sys.stderr)
        print("Spróbuj: python -m playwright install chromium"
              + ("" if args.channel else "  albo dodaj --channel msedge"), file=sys.stderr)
        return 3
    with renderer:
        for index, url in enumerate(urls, start=1):
            prefix = f"[{index}/{len(urls)}] {url}"

            # Ograniczenie tempa per host: --delay albo Crawl-delay z robots.txt (większe).
            host = urlsplit(normalize_url(url) or url).hostname or ""
            wait = args.delay
            crawl_delay = renderer.robots.policy_for(normalize_url(url)).crawl_delay() if renderer.robots else None
            if crawl_delay:
                wait = max(wait, crawl_delay)
            if host in last_visit:
                remaining = wait - (time.monotonic() - last_visit[host])
                if remaining > 0:
                    time.sleep(remaining)

            try:
                snapshot = renderer.render(url)
            except RobotsDisallowedError as exc:
                print(f"{prefix}\n    POMINIĘTO: {exc}", file=sys.stderr)
                failures += 1
                continue
            except RenderError as exc:
                print(f"{prefix}\n    BŁĄD: {exc}", file=sys.stderr)
                failures += 1
                continue
            except Exception as exc:  # jedna zepsuta strona nie przerywa całego przebiegu
                print(f"{prefix}\n    NIEOCZEKIWANY BŁĄD: {type(exc).__name__}: {exc}", file=sys.stderr)
                failures += 1
                continue
            finally:
                last_visit[host] = time.monotonic()

            folder = save_snapshot(snapshot, args.out, name=args.name)
            print(
                f"{prefix}\n"
                f"    OK  HTTP {snapshot.http_status}  {snapshot.render_ms} ms  \"{snapshot.title[:60]}\"\n"
                f"    linki wewnętrzne: {len(snapshot.links_internal)}, "
                f"zablokowane robots.txt: {len(snapshot.links_blocked_by_robots)}, "
                f"dokumenty: {len(snapshot.documents)}\n"
                f"    baner cookies: {_banner_summary(snapshot.cookie_banner)}\n"
                f"    zapisano: {folder}"
            )
            for warning in snapshot.warnings:
                print(f"    uwaga: {warning}")

    ok = len(urls) - failures
    print(f"\nGotowe: {ok} z {len(urls)} stron zapisanych.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
