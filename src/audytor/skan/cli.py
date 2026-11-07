"""Komenda „skanuj adres”: render -> axe-core -> migawka + wynik.json (opcjonalnie zapis w bazie).

Przykłady:
    audytor-scan https://www.wasilkow.pl/
    python -m audytor.skan https://pb.edu.pl https://www.gov.pl --out wyniki
    python -m audytor.skan https://pb.edu.pl --db sqlite:///audytor.db
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from audytor.crawler.links import normalize_url
from audytor.crawler.render import Renderer, RenderError, RenderOptions, RobotsDisallowedError
from audytor.wyniki import WynikStrony

from .przebieg import SkanError, skanuj_strone

DEFAULT_OUT = Path("wyniki")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audytor-scan",
        description="Skanuje strony: renderuje (Playwright), uruchamia axe-core (WCAG 2.1 A/AA) "
        "i zapisuje migawkę oraz wynik.json we wspólnym formacie.",
    )
    parser.add_argument("urls", nargs="*", metavar="URL", help="adresy stron do sprawdzenia")
    parser.add_argument("--urls-file", type=Path, help="plik z adresami, jeden w linii (# = komentarz)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"folder wyników (domyślnie {DEFAULT_OUT})")
    parser.add_argument("--name", help="nazwa folderu wyniku (tylko przy jednym adresie)")
    parser.add_argument("--db", metavar="URL_BAZY",
                        help="zapisz wyniki także w bazie, np. sqlite:///audytor.db albo postgresql://...")
    parser.add_argument("--delay", type=float, default=1.0, help="pauza między stronami w sekundach (domyślnie 1)")
    parser.add_argument("--timeout", type=float, default=30.0, help="limit wczytania strony w sekundach (domyślnie 30)")
    parser.add_argument("--png", action="store_true", help="zrzut jako PNG (domyślnie JPEG – mniejszy plik)")
    parser.add_argument("--mhtml", action="store_true", help="zapisz też kopię MHTML strony (duży plik)")
    parser.add_argument("--ignore-robots", action="store_true", help="NIE sprawdzaj robots.txt (tylko do testów własnych stron)")
    parser.add_argument("--keep-cookie-banner", action="store_true",
                        help="nie zamykaj banera cookies (axe sprawdzi stronę razem z banerem)")
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


def _podsumowanie(wynik: WynikStrony) -> str:
    p = wynik.podsumowanie()
    wagi = ", ".join(f"{waga}: {n}" for waga, n in p["wg_wagi"].items() if n)
    return (f"błędy: {p['wg_statusu']['blad']}, do weryfikacji: {p['wg_statusu']['do_weryfikacji']}"
            + (f"  ({wagi})" if wagi else ""))


def _otworz_baze(url_bazy: str):
    from audytor.db import otworz_baze  # SQLAlchemy potrzebny tylko z --db

    return otworz_baze(url_bazy)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    urls = _read_urls(args, parser)

    sesje = None
    if args.db:
        try:
            sesje = _otworz_baze(args.db)
        except Exception as exc:
            print(f"Nie udało się połączyć z bazą {args.db}: {str(exc).splitlines()[0]}", file=sys.stderr)
            return 2

    options = RenderOptions(
        timeout_ms=int(args.timeout * 1000),
        screenshot_type="png" if args.png else "jpeg",
        save_mhtml=args.mhtml,
        respect_robots=not args.ignore_robots,
        channel=args.channel,
        dismiss_cookies=not args.keep_cookie_banner,
    )
    try:
        renderer = Renderer(options, headless=not args.headed)
        renderer.start()
    except Exception as exc:
        print(f"Nie udało się uruchomić przeglądarki: {str(exc).splitlines()[0]}", file=sys.stderr)
        print("Spróbuj: python -m playwright install chromium"
              + ("" if args.channel else "  albo dodaj --channel msedge"), file=sys.stderr)
        return 3

    wyniki: list[WynikStrony] = []
    failures = 0
    last_visit: dict[str, float] = {}
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
                wynik, folder = skanuj_strone(renderer, url, args.out, name=args.name)
            except RobotsDisallowedError as exc:
                print(f"{prefix}\n    POMINIĘTO: {exc}", file=sys.stderr)
                failures += 1
                continue
            except (RenderError, SkanError) as exc:
                print(f"{prefix}\n    BŁĄD: {exc}", file=sys.stderr)
                failures += 1
                continue
            except Exception as exc:  # jedna zepsuta strona nie przerywa całego przebiegu
                print(f"{prefix}\n    NIEOCZEKIWANY BŁĄD: {type(exc).__name__}: {exc}", file=sys.stderr)
                failures += 1
                continue
            finally:
                last_visit[host] = time.monotonic()

            wyniki.append(wynik)
            print(f"{prefix}\n    OK  HTTP {wynik.http_status}  {_podsumowanie(wynik)}\n    zapisano: {folder}")
            for warning in wynik.ostrzezenia:
                print(f"    uwaga: {warning}")

    if sesje is not None and wyniki:
        from audytor.db import zapisz_skan

        with sesje() as sesja:
            skan = zapisz_skan(sesja, wyniki, url_startowy=urls[0])
            sesja.commit()
            print(f"\nZapisano w bazie: skan #{skan.id}, podstron: {len(wyniki)}.")

    print(f"\nGotowe: {len(urls) - failures} z {len(urls)} stron sprawdzonych.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
