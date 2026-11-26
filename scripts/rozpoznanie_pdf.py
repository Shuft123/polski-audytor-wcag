"""Rozpoznanie audytu PDF (sprint 2, osoba 2): podstawowe sprawdzenia dostępności PDF przez pikepdf.

To NIE jest moduł produkcyjny – prototyp do notatki docs/rozpoznanie-pdf.md. Sprawdza kilka reguł
PDF/UA-1, które da się zweryfikować maszynowo bez Javy, i porównuje wyniki z korpusem veraPDF.

Użycie:
    pip install pikepdf
    python scripts/rozpoznanie_pdf.py plik.pdf [kolejny.pdf ...]       # raport JSON dla plików
    python scripts/rozpoznanie_pdf.py --korpus <folder veraPDF-corpus/PDF_UA-1>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pikepdf

# Sprawdzenie -> (reguła PDF/UA-1 w profilu veraPDF, kryterium WCAG 2.1 / technika PDF)
REGULY = {
    "otagowany": ("7.1-11", "1.3.1 (PDF1, PDF9)"),
    "bez_suspects": ("7.1-4", "1.3.1"),
    "metadane_xmp": ("7.1-8", "–"),
    "tytul": ("7.1-9", "2.4.2 (PDF18)"),
    "wyswietla_tytul": ("7.1-10", "2.4.2 (PDF18)"),
    "jezyk": ("7.2-34 (część)", "3.1.1 (PDF16)"),
    "alt_ilustracji": ("7.3-1", "1.1.1 (PDF1)"),
    "identyfikator_pdfua": ("5-1", "–"),
    "tekst_nie_skan": ("–", "1.1.1, 1.4.5 (PDF7)"),
}

_OPERATORY_TEKSTU = {"Tj", "TJ", "'", '"'}


def _bool(wartosc) -> bool:
    return bool(wartosc) if wartosc is not None else False


def _figury(struct_tree) -> tuple[int, int]:
    """(liczba elementów Figure, ile z nich bez /Alt i /ActualText) – przejście drzewa struktury."""
    figury = bez_alt = 0
    stos = [struct_tree.get("/K")]
    widziane: set[tuple[int, int]] = set()
    while stos:
        el = stos.pop()
        if el is None:
            continue
        if isinstance(el, pikepdf.Array):
            stos.extend(el)
            continue
        if not isinstance(el, pikepdf.Dictionary):
            continue
        if el.is_indirect:
            if el.objgen in widziane:
                continue
            widziane.add(el.objgen)
        if el.get("/S") == pikepdf.Name("/Figure"):
            figury += 1
            # Jak reguła veraPDF 7.3-1: niepusty Alt albo obecny ActualText (także pusty).
            # Pusty Alt="" to błąd (korpus: 7.3-t01-fail-b), pusty ActualText – nie (7.3-t01-pass-c).
            if not str(el.get("/Alt", "")).strip() and "/ActualText" not in el:
                bez_alt += 1
        if "/K" in el:
            stos.append(el["/K"])
    return figury, bez_alt


def _strony_bez_tekstu(pdf: pikepdf.Pdf) -> tuple[int, int]:
    """(liczba stron, ile stron ma obrazy, a nie ma operatorów tekstu) – przybliżenie „skan bez OCR”."""
    bez_tekstu = 0
    for strona in pdf.pages:
        try:
            operatory = {str(op) for _, op in pikepdf.parse_content_stream(strona)}
        except pikepdf.PdfError:
            operatory = set()
        ma_tekst = bool(operatory & _OPERATORY_TEKSTU)
        ma_obraz = "Do" in operatory or "BI" in operatory
        if ma_obraz and not ma_tekst:
            bez_tekstu += 1
    return len(pdf.pages), bez_tekstu


def sprawdz(sciezka: Path) -> dict:
    with pikepdf.open(sciezka) as pdf:
        kat = pdf.Root
        mark = kat.get("/MarkInfo", {})
        struct = kat.get("/StructTreeRoot")
        tytul = pdfua = None
        if "/Metadata" in kat:
            try:
                with pdf.open_metadata() as meta:
                    tytul = meta.get("dc:title")
                    pdfua = meta.get("pdfuaid:part")
            except Exception:
                pass
        pref = kat.get("/ViewerPreferences", {})
        figury, bez_alt = _figury(struct) if struct is not None else (0, 0)
        strony, bez_tekstu = _strony_bez_tekstu(pdf)
        lang = str(kat.get("/Lang", "")).strip()
        wynik = {
            "otagowany": struct is not None and _bool(mark.get("/Marked")),
            "bez_suspects": not _bool(mark.get("/Suspects")),
            "metadane_xmp": "/Metadata" in kat,
            "tytul": bool(tytul and str(tytul).strip()),
            "wyswietla_tytul": _bool(pref.get("/DisplayDocTitle")),
            "jezyk": bool(lang),
            "alt_ilustracji": bez_alt == 0,
            "identyfikator_pdfua": pdfua is not None,
            "tekst_nie_skan": bez_tekstu == 0,
        }
        wynik["_szczegoly"] = {"lang": lang or None, "figury": figury, "figury_bez_alt": bez_alt,
                               "strony": strony, "strony_bez_tekstu": bez_tekstu}
        return wynik


# Plik korpusu veraPDF "7.1-t09-fail-a.pdf" -> reguła "7.1-9", oczekiwany wynik False
_PLIK_KORPUSU = re.compile(r"^(\d+\.\d+|\d+)-t(\d+)-(pass|fail)-[a-z]\.pdf$")


def korpus(folder: Path) -> dict:
    """Zgodność sprawdzeń z korpusem veraPDF dla reguł, które implementujemy."""
    regula_na_test = {r.split()[0]: nazwa for nazwa, (r, _) in REGULY.items() if r != "–"}
    wyniki: dict[str, dict[str, int]] = {}
    for plik in sorted(folder.rglob("*.pdf")):
        m = _PLIK_KORPUSU.match(plik.name)
        if not m:
            continue
        regula = f"{m.group(1)}-{int(m.group(2))}"
        nazwa = regula_na_test.get(regula)
        if nazwa is None:
            continue
        oczekiwane = m.group(3) == "pass"
        try:
            otrzymane = sprawdz(plik)[nazwa]
        except Exception as exc:  # uszkodzone pliki testowe
            print(f"{plik.name}: błąd odczytu – {exc}", file=sys.stderr)
            continue
        stat = wyniki.setdefault(f"{regula} {nazwa}", {"plikow": 0, "zgodnych": 0})
        stat["plikow"] += 1
        stat["zgodnych"] += int(otrzymane == oczekiwane)
        if otrzymane != oczekiwane:
            print(f"niezgodność: {plik.name} – {nazwa} = {otrzymane}, oczekiwano {oczekiwane}", file=sys.stderr)
    return wyniki


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pliki", nargs="*", type=Path)
    parser.add_argument("--korpus", type=Path, help="folder PDF_UA-1 z repozytorium veraPDF-corpus")
    args = parser.parse_args(argv)
    if args.korpus:
        print(json.dumps(korpus(args.korpus), ensure_ascii=False, indent=2))
    for plik in args.pliki:
        print(json.dumps({"plik": str(plik), **sprawdz(plik)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
