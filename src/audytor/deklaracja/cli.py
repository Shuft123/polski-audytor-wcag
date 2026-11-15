"""Wyszukiwanie deklaracji dostępności z wiersza poleceń (F17).

Przykłady:
    # bez sieci – na migawkach crawlera
    python -m audytor.deklaracja --snapshot tests/data/snapshots/pb-edu-pl
    python -m audytor.deklaracja --snapshot tests/data/snapshots/*

    # z siecią – pobiera stronę główną i weryfikuje kandydatów (identyfikatory a11y-*)
    python -m audytor.deklaracja https://www.wasilkow.pl
    python -m audytor.deklaracja --urls-file tests/data/strony-testowe-deklaracja.csv --csv wyniki.csv

    # strona główna zawsze renderowana w przeglądarce (domyślnie tylko gdy trzeba)
    python -m audytor.deklaracja https://www.x-kom.pl --render

Gdy jest zainstalowany Playwright, przeglądarka włącza się sama przy błędzie certyfikatu SSL,
blokadzie botów (HTTP 403/429/503) i stronie głównej z bardzo małą liczbą linków.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from .wyszukiwanie import (
    STATUS_NO_A11Y,
    STATUS_NONE,
    BrowserFetcher,
    DeclarationResult,
    find_declaration,
    find_in_html,
    main_reason,
)

_LABELS = {STATUS_NONE: "BRAK", STATUS_NO_A11Y: "BEZ_A11Y"}


def use_system_certificates() -> bool:
    """Weryfikacja SSL przez magazyn certyfikatów systemu (pakiet truststore).

    Windows i macOS same uzupełniają niepełne łańcuchy certyfikatów (częste na stronach
    urzędów), a domyślny Python tego nie robi i zgłasza CERTIFICATE_VERIFY_FAILED.
    Dotyczy całego procesu, więc także pobierania robots.txt.
    """
    try:
        import truststore
    except ImportError:
        return False
    truststore.inject_into_ssl()
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m audytor.deklaracja",
        description="Szuka linku do deklaracji dostępności na stronie głównej i (opcjonalnie) "
        "sprawdza, czy wskazana strona ma identyfikatory a11y-* z warunków technicznych.",
    )
    parser.add_argument("urls", nargs="*", metavar="URL", help="adresy stron głównych")
    parser.add_argument("--urls-file", type=Path,
                        help="plik z adresami: .txt (jeden w linii, # = komentarz) albo .csv z kolumną 'url'")
    parser.add_argument("--snapshot", type=Path, nargs="+", default=[],
                        help="folder(y) migawek crawlera (dom.html + meta.json) – bez sieci, chyba że --sprawdz")
    parser.add_argument("--sprawdz", action="store_true",
                        help="przy --snapshot: pobierz kandydatów i sprawdź identyfikatory a11y-*")
    parser.add_argument("--bez-weryfikacji", action="store_true",
                        help="przy adresach URL: tylko pobierz stronę główną, nie sprawdzaj kandydatów")
    parser.add_argument("--render", action="store_true",
                        help="zawsze renderuj stronę główną w przeglądarce (Playwright)")
    parser.add_argument("--bez-przegladarki", action="store_true",
                        help="nie używaj przeglądarki nawet przy błędach SSL / blokadzie botów")
    parser.add_argument("--delay", type=float, default=1.0, help="pauza między zapytaniami w sekundach (domyślnie 1)")
    parser.add_argument("--ignore-robots", action="store_true", help="NIE sprawdzaj robots.txt (tylko własne strony)")
    parser.add_argument("--out", type=Path, help="zapisz pełny wynik JSON do pliku")
    parser.add_argument("--csv", type=Path, help="zapisz podsumowanie (jedna strona = jeden wiersz) do CSV")
    parser.add_argument("--kandydaci", type=int, default=3, help="ilu kandydatów pokazać w JSON (domyślnie 3)")
    return parser


def read_urls_file(path: Path) -> list[str]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8", newline="") as fh:
            rows = csv.DictReader(line for line in fh if not line.lstrip().startswith("#"))
            return [row["url"].strip() for row in rows if row.get("url", "").strip()]
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def _from_snapshot(folder: Path, verify: bool, delay: float, respect_robots: bool,
                   browser: BrowserFetcher | None = None) -> DeclarationResult:
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    dom_name = meta.get("files", {}).get("dom", "dom.html")
    html = (folder / dom_name).read_text(encoding="utf-8")
    page_url = meta.get("final_url") or meta["requested_url"]
    if verify:
        return find_declaration(page_url, html=html, delay=delay, respect_robots=respect_robots, browser=browser)
    return find_in_html(html, page_url)


def _summary_row(result: DeclarationResult) -> dict:
    return {
        "url": result.site_url,
        "znaleziono": "tak" if result.found else "nie",
        "deklaracja_url": result.declaration_url or "",
        "metoda": result.method,
        "pewnosc": result.confidence,
        "stan": result.status,
        "zweryfikowano": "tak" if result.verified else "nie",
        "liczba_a11y": len(result.a11y_ids),
        "brakujace_obowiazkowe_a11y": " ".join(result.missing_required_ids),
        "uwagi": " | ".join(result.warnings),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    urls = list(args.urls)
    if args.urls_file:
        urls += read_urls_file(args.urls_file)
    if not urls and not args.snapshot:
        build_parser().print_usage(sys.stderr)
        print("Podaj adres URL, --urls-file albo --snapshot.", file=sys.stderr)
        return 2

    respect_robots = not args.ignore_robots
    certs = use_system_certificates()
    if not certs and urls:
        print("[uwaga] brak pakietu truststore – strony z niepełnym łańcuchem certyfikatów "
              "mogą zgłaszać błąd SSL (pip install truststore)", file=sys.stderr)
    browser = None
    if not args.bez_przegladarki and BrowserFetcher.available():
        browser = BrowserFetcher()
    elif args.render:
        print("[uwaga] --render wymaga Playwrighta (pip install playwright; "
              "python -m playwright install chromium)", file=sys.stderr)

    results: list[DeclarationResult] = []
    try:
        for folder in args.snapshot:
            if not (folder / "meta.json").exists():
                print(f"[pomijam] {folder}: brak meta.json", file=sys.stderr)
                continue
            results.append(_from_snapshot(folder, args.sprawdz, args.delay, respect_robots, browser))

        for url in urls:
            print(f"[deklaracja] {url}", file=sys.stderr)
            html = None
            if args.render and browser is not None:
                try:
                    _, url, html = browser(url)
                except OSError as exc:
                    print(f"  renderowanie nieudane ({exc}); próbuję bez przeglądarki", file=sys.stderr)
            results.append(find_declaration(
                url, html=html, verify=not args.bez_weryfikacji,
                delay=args.delay, respect_robots=respect_robots, browser=browser,
            ))
    finally:
        if browser is not None:
            browser.close()

    payload = []
    for result in results:
        data = result.to_dict()
        data["candidates"] = data["candidates"][: args.kandydaci]
        payload.append(data)
        label = _LABELS.get(result.status, "OK")
        print(f"{label:<8} {result.site_url} -> {result.declaration_url or '-'} "
              f"({result.method}, pewność {result.confidence})", file=sys.stderr)
        reason = main_reason(result)
        if result.status in (STATUS_NONE, STATUS_NO_A11Y) and reason:
            print(f"         powód: {reason}", file=sys.stderr)

    text = json.dumps(payload if len(payload) != 1 else payload[0], ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)

    if args.csv:
        with args.csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(_summary_row(results[0]).keys()) if results else ["url"])
            writer.writeheader()
            for result in results:
                writer.writerow(_summary_row(result))
    return 0
