"""Prototyp raportu PDF (F22, sprint 2): ten sam fragment raportu w WeasyPrint (PDF/UA-1) i ReportLab.

Porównuje strukturę obu plików (tagi, alt obrazu, język, oznaczenie PDF/UA) – wyniki w
docs/rozpoznanie-raport-pdf.md. Biblioteki nie są zależnościami projektu:

    pip install weasyprint reportlab pikepdf
    python scripts/prototyp_raport_pdf.py wyniki/prototyp-raportu
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PIKSEL = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
HTML = f"""<!doctype html><html lang="pl"><head><meta charset="utf-8"><title>Raport dostępności – przykład</title>
<style>@page {{ size: A4; margin: 2cm; @bottom-right {{ content: "Strona " counter(page) " z " counter(pages) }} }}
body {{ font-family: sans-serif }} table {{ border-collapse: collapse }}
th, td {{ border: 1px solid #444; padding: 4px }}
</style></head><body>
<h1>Raport dostępności cyfrowej</h1>
<p>Witryna: https://www.wasilkow.pl/ – skan przykładowy. Zażółć gęślą jaźń.</p>
<h2>Podsumowanie</h2>
<table><caption>Problemy według kryterium WCAG</caption>
<thead><tr><th scope="col">Kryterium</th><th scope="col">Błędy</th><th scope="col">Do weryfikacji</th></tr></thead>
<tbody><tr><td>1.1.1 Treść nietekstowa</td><td>12</td><td>4</td></tr>
<tr><td>2.4.7 Widoczny fokus</td><td>0</td><td>7</td></tr></tbody></table>
<h2>Zrzut strony startowej</h2>
<img src="data:image/png;base64,{PIKSEL}" alt="Zrzut ekranu strony startowej z zaznaczonymi błędami"
     width="200" height="120">
</body></html>"""


def weasyprint_ua(plik: Path) -> None:
    from weasyprint import HTML as WeasyHTML

    WeasyHTML(string=HTML).write_pdf(plik, pdf_variant="pdf/ua-1")


def reportlab(plik: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table

    style = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(plik), pagesize=A4, title="Raport dostępności", lang="pl")
    doc.build([
        Paragraph("Raport dostępności cyfrowej", style["Title"]),
        Paragraph("Zażółć gęślą jaźń.", style["Normal"]),
        Table([["Kryterium", "Błędy", "Do weryfikacji"], ["1.1.1", "12", "4"], ["2.4.7", "0", "7"]]),
    ])


def struktura(plik: Path) -> dict:
    """Co z dostępności PDF widać w pliku: drzewo tagów, alt rysunków, język, oznaczenie PDF/UA."""
    import pikepdf

    tagi: set[str] = set()
    alty: list[str] = []

    def przejdz(element, glebokosc: int = 0) -> None:
        if glebokosc > 20:
            return
        typ = element.get("/S")
        if typ is not None:
            tagi.add(str(typ).lstrip("/"))
            if str(typ) == "/Figure" and element.get("/Alt") is not None:
                alty.append(str(element.get("/Alt")))
        dzieci = element.get("/K")
        for dziecko in dzieci if isinstance(dzieci, pikepdf.Array) else [dzieci]:
            if isinstance(dziecko, pikepdf.Dictionary):
                przejdz(dziecko, glebokosc + 1)

    with pikepdf.open(plik) as pdf:
        root = pdf.Root
        if "/StructTreeRoot" in root:
            przejdz(root.StructTreeRoot)
        return {
            "tagged_pdf": "/StructTreeRoot" in root,
            "jezyk": str(root.get("/Lang")) if root.get("/Lang") is not None else None,
            "pdf_ua": pdf.open_metadata().get("pdfuaid:part"),
            "tagi": sorted(tagi),
            "alty": alty,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="gdzie zapisać przykładowe PDF-y")
    args = parser.parse_args(argv)
    args.folder.mkdir(parents=True, exist_ok=True)
    try:
        for nazwa, funkcja in (("weasyprint-pdf-ua.pdf", weasyprint_ua), ("reportlab.pdf", reportlab)):
            plik = args.folder / nazwa
            start = time.perf_counter()
            funkcja(plik)
            czas = time.perf_counter() - start
            print(f"{nazwa} ({czas:.2f} s): {struktura(plik)}")
    except ImportError as exc:
        print(f"Brak biblioteki: {exc.name} – pip install weasyprint reportlab pikepdf", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
