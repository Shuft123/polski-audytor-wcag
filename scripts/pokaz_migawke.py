"""Czytelne podsumowanie migawki (meta.json) – używane w pokazie sprintu.

Użycie: python scripts/pokaz_migawke.py tests/data/snapshots/pb-edu-pl
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from audytor.crawler import load_meta  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    folder = Path(sys.argv[1])
    try:
        meta = load_meta(folder)
    except FileNotFoundError:
        print(f"Brak pliku meta.json w {folder}")
        return 1

    links = meta["links"]
    banner = meta.get("cookie_banner", {})
    if not banner.get("checked"):
        banner_text = "nie sprawdzano"
    elif not banner.get("detected"):
        banner_text = "nie wykryto"
    elif banner.get("dismissed"):
        banner_text = f"zamknięty przyciskiem „{banner.get('button_text')}”"
    else:
        banner_text = "wykryty, ale NIE zamknięty (brak przycisku odrzucenia)"

    print(f"  Strona:            {meta['title']}")
    print(f"  Adres:             {meta['final_url']}")
    print(f"  Kod HTTP:          {meta['http_status']}    czas renderowania: {meta['render_ms']} ms")
    print(f"  Język (lang):      {meta['lang'] or '(brak – błąd WCAG 3.1.1)'}")
    print(f"  robots.txt:        {meta['robots']['status']}  ({meta['robots']['robots_url']})")
    print(f"  Baner cookies:     {banner_text}")
    print(f"  Linki wewnętrzne:  {len(links['internal'])}")
    for url in links["internal"][:5]:
        print(f"      {url}")
    if len(links["internal"]) > 5:
        print(f"      ... i {len(links['internal']) - 5} więcej")
    print(f"  Zablokowane przez robots.txt: {len(links['blocked_by_robots'])}")
    print(f"  Linki do dokumentów (PDF/DOC): {len(links['documents'])}")
    print(f"  Linki zewnętrzne:  {links['external_count']}")
    print(f"  Pliki migawki:     {', '.join(meta['files'].values())}")
    for warning in meta.get("warnings", []):
        print(f"  Uwaga: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
