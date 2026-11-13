"""Test fokusu z wiersza poleceń.

Przykłady:
    python -m audytor.fokus https://pb.edu.pl/
    python -m audytor.fokus https://www.gov.pl/ --max-krokow 40 --out wyniki/fokus
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from audytor.crawler import slug_for_url
from audytor.crawler.render import Renderer, RenderError, RenderOptions, RobotsDisallowedError

from .tab import mapa_fokusu, przejdz_tabem

DEFAULT_OUT = Path("wyniki") / "fokus"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m audytor.fokus",
        description="Przechodzi stronę klawiszem Tab, porównuje zrzuty z fokusem i bez "
        "i ocenia widoczność fokusu (WCAG 2.4.7).",
    )
    parser.add_argument("url", help="adres strony")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"folder wyjściowy (domyślnie {DEFAULT_OUT})")
    parser.add_argument("--max-krokow", type=int, default=60, help="maks. liczba naciśnięć Tab (domyślnie 60)")
    parser.add_argument("--timeout", type=float, default=30.0, help="limit wczytania strony w sekundach")
    parser.add_argument("--bez-zrzutow", action="store_true", help="nie zapisuj obrazów porównania i mapy fokusu")
    parser.add_argument("--ignore-robots", action="store_true", help="NIE sprawdzaj robots.txt (tylko własne strony testowe)")
    parser.add_argument("--headed", action="store_true", help="pokaż okno przeglądarki")
    parser.add_argument("--channel", choices=["msedge", "chrome"], help="przeglądarka z systemu zamiast Chromium z Playwrighta")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_krokow < 1:
        print("--max-krokow musi być >= 1", file=sys.stderr)
        return 2

    options = RenderOptions(
        timeout_ms=int(args.timeout * 1000),
        save_mhtml=False,
        respect_robots=not args.ignore_robots,
        channel=args.channel,
    )
    try:
        renderer = Renderer(options, headless=not args.headed)
        renderer.start()
    except Exception as exc:  # noqa: BLE001 – brak przeglądarki itp.
        print(f"Nie udało się uruchomić przeglądarki: {exc}", file=sys.stderr)
        return 3

    try:
        with renderer.open(args.url) as opened:
            folder = args.out / slug_for_url(opened.final_url)
            wynik = przejdz_tabem(
                opened.page,
                url=opened.final_url,
                max_krokow=args.max_krokow,
                folder_zrzutow=None if args.bez_zrzutow else folder / "kroki",
            )
            wynik.ostrzezenia = opened.warnings + wynik.ostrzezenia
            folder.mkdir(parents=True, exist_ok=True)
            if not args.bez_zrzutow:
                mapa_fokusu(opened.page, wynik).save(folder / "mapa-fokusu.png")
    except (RenderError, RobotsDisallowedError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    finally:
        renderer.close()

    plik = folder / "fokus.json"
    plik.write_text(json.dumps(wynik.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    p = wynik.podsumowanie()
    print(f"{wynik.url}: {p['kroki']} elementów w kolejności Tab – {wynik.zakonczenie}")
    print(f"  fokus widoczny: {p['ok']}, słaby: {p['slaby']}, brak: {p['brak']}, poza ekranem: {p['niewidoczny']}, zgubiony: {p['zgubiony']}")
    print(f"  problemy do weryfikacji: {len(wynik.problemy)}")
    print(f"  wynik: {plik}")
    return 0
