"""Strona pokazowa sprintu 1 – narzędzie do prezentacji, NIE część audytora (to nie dashboard F23).

Uruchomienie (w głównym folderze repozytorium, z zainstalowanym projektem):
    python scripts/demo_strona/serwer.py            # otwiera http://localhost:8050 w przeglądarce
    python scripts/demo_strona/serwer.py --port 8060 --bez-przegladarki

Strona tylko WYWOŁUJE istniejące moduły (crawler, skan/axe, fokus, deklaracja) – niczego w nich
nie zmienia i nic z projektu jej nie importuje. Nie używa bazy, Redisa ani Dockera.
Wyniki zapisuje w demo-wyniki/ (folder jest w .gitignore). Usunięcie folderu scripts/demo_strona/
usuwa stronę bez wpływu na resztę projektu.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

KATALOG = Path(__file__).resolve().parent
REPO = KATALOG.parents[1]
sys.path.insert(0, str(REPO / "src"))  # działa też bez `pip install -e .`

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from audytor.crawler.render import Renderer, RenderError, RenderOptions, RobotsDisallowedError  # noqa: E402
from audytor.crawler.snapshot import save_snapshot, slug_for_url  # noqa: E402

WYNIKI = REPO / "demo-wyniki"
PLIK_ALT = REPO / "docs" / "wyniki" / "alt_wyniki_v3.csv"
ADRES_BACKENDU = "http://localhost:8000"

app = FastAPI(title="Polski audytor WCAG – pokaz sprintu 1", docs_url=None, redoc_url=None)
_blokada = threading.Lock()   # jedna akcja naraz – jedna przeglądarka, przewidywalne czasy
_kanal: str | None = None      # None = Chromium z Playwrighta; "msedge" po nieudanym starcie


class Zadanie(BaseModel):
    url: str
    max_krokow: int = 20


# --- pomocnicze -------------------------------------------------------------------------

def _renderer() -> Renderer:
    """Uruchomiona przeglądarka; gdy wbudowany Chromium nie startuje – Edge z systemu."""
    global _kanal
    for kanal in ([_kanal] if _kanal else [None, "msedge"]):
        renderer = Renderer(RenderOptions(screenshot_type="jpeg", save_mhtml=False, channel=kanal))
        try:
            renderer.start()
        except Exception:  # noqa: BLE001 – brak przeglądarki / błąd startu
            continue
        _kanal = kanal
        return renderer
    raise HTTPException(500, "Nie udało się uruchomić przeglądarki. "
                             "Uruchom: python -m playwright install chromium")


def _link(sciezka: Path) -> str:
    """Adres pliku z demo-wyniki/ dla przeglądarki (z parametrem przeciw cache)."""
    return f"/pliki/{sciezka.relative_to(WYNIKI).as_posix()}?t={int(time.time() * 1000)}"


def _pliki_migawki(folder: Path, meta: dict[str, Any]) -> dict[str, str]:
    pliki = meta.get("files", {})
    linki = {}
    for klucz in ("screenshot", "cookie_banner_screenshot", "dom"):
        if klucz in pliki and (folder / pliki[klucz]).exists():
            linki[klucz] = _link(folder / pliki[klucz])
    return linki


def _wykonaj(funkcja, *args) -> dict[str, Any]:
    """Uruchamia akcję z przeglądarką, zamienia błędy na czytelne komunikaty."""
    if not _blokada.acquire(timeout=1):
        raise HTTPException(409, "Trwa inna akcja – poczekaj, aż się skończy.")
    poczatek = time.monotonic()
    try:
        renderer = _renderer()
        try:
            wynik = funkcja(renderer, *args)
        finally:
            renderer.close()
    except RobotsDisallowedError as exc:
        raise HTTPException(400, f"Pominięto: {exc}") from exc
    except RenderError as exc:
        raise HTTPException(400, f"Nie udało się otworzyć strony: {exc}") from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 – pokaz ma pokazać błąd, a nie się wysypać
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc
    finally:
        _blokada.release()
    wynik["czas_s"] = round(time.monotonic() - poczatek, 1)
    if _kanal:
        wynik.setdefault("uwagi", []).append(f"Użyto przeglądarki z systemu: {_kanal}")
    return wynik


# --- akcje (każda = moduł innej osoby) ----------------------------------------------------

def _migawka(renderer: Renderer, url: str) -> dict[str, Any]:
    """Osoba 1 – crawler: render, zrzut, linki, robots.txt, baner cookies."""
    snapshot = renderer.render(url)
    folder = save_snapshot(snapshot, WYNIKI / "migawki")
    meta = snapshot.meta()
    return {"meta": meta, "pliki": _pliki_migawki(folder, meta)}


def _skan(renderer: Renderer, url: str) -> dict[str, Any]:
    """Osoba 2 – axe-core na wyrenderowanej stronie, wynik.json we wspólnym formacie."""
    from audytor.skan.przebieg import SkanError, skanuj_strone

    try:
        wynik, folder = skanuj_strone(renderer, url, WYNIKI / "skany")
    except SkanError as exc:
        raise HTTPException(500, str(exc)) from exc
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    return {"wynik": wynik.to_dict(), "pliki": _pliki_migawki(folder, meta)}


def _fokus(renderer: Renderer, url: str, max_krokow: int) -> dict[str, Any]:
    """Osoba 4 – przejście stroną klawiszem Tab i ocena widoczności fokusu (WCAG 2.4.7)."""
    from audytor.fokus.tab import mapa_fokusu, przejdz_tabem

    with renderer.open(url) as opened:
        folder = WYNIKI / "fokus" / slug_for_url(opened.final_url)
        folder.mkdir(parents=True, exist_ok=True)
        wynik = przejdz_tabem(opened.page, url=opened.final_url, max_krokow=max_krokow, folder_zrzutow=None)
        wynik.ostrzezenia = opened.warnings + wynik.ostrzezenia
        mapa = folder / "mapa-fokusu.png"
        mapa_fokusu(opened.page, wynik).save(mapa)
    dane = wynik.to_dict()
    (folder / "fokus.json").write_text(json.dumps(dane, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"wynik": dane, "pliki": {"mapa": _link(mapa)}}


def _deklaracja(renderer: Renderer, url: str) -> dict[str, Any]:
    """Osoba 5 – wyszukanie linku do deklaracji dostępności i sprawdzenie identyfikatorów a11y-*."""
    from audytor.deklaracja import find_declaration

    with renderer.open(url) as opened:
        final_url, html = opened.final_url, opened.page.content()
    wynik = find_declaration(final_url, html=html)
    return {"wynik": wynik.to_dict()}


# --- API strony --------------------------------------------------------------------------

@app.get("/")
def strona() -> FileResponse:
    return FileResponse(KATALOG / "strona.html", media_type="text/html; charset=utf-8")


@app.post("/api/migawka")
def api_migawka(z: Zadanie) -> dict[str, Any]:
    return _wykonaj(_migawka, z.url)


@app.post("/api/skan")
def api_skan(z: Zadanie) -> dict[str, Any]:
    return _wykonaj(_skan, z.url)


@app.post("/api/fokus")
def api_fokus(z: Zadanie) -> dict[str, Any]:
    return _wykonaj(_fokus, z.url, max(1, min(z.max_krokow, 60)))


@app.post("/api/deklaracja")
def api_deklaracja(z: Zadanie) -> dict[str, Any]:
    return _wykonaj(_deklaracja, z.url)


@app.get("/api/alt")
def api_alt() -> dict[str, Any]:
    """Osoba 3 – WYNIKI zapisane z notatnika Colab (model Bielik nie jest uruchamiany na żywo)."""
    if not PLIK_ALT.exists():
        raise HTTPException(404, f"Brak pliku {PLIK_ALT.relative_to(REPO)}")
    with PLIK_ALT.open(encoding="utf-8") as plik:
        wiersze = list(csv.DictReader(plik))
    ai = [w for w in wiersze if w.get("zrodlo") == "ai"]
    return {
        "plik": PLIK_ALT.relative_to(REPO).as_posix(),
        "wiersze": wiersze,
        "podsumowanie": {
            "przykladow": len(wiersze),
            "trafionych": sum(w.get("trafiony") == "True" for w in wiersze),
            "reguly": len(wiersze) - len(ai),
            "ai": len(ai),
            "ai_trafionych": sum(w.get("trafiony") == "True" for w in ai),
        },
    }


@app.get("/api/backend")
def api_backend() -> dict[str, Any]:
    """Osoba 6 – czy działa API z docker-compose (GET /health na porcie 8000)."""
    try:
        with urllib.request.urlopen(f"{ADRES_BACKENDU}/health", timeout=2) as odp:
            return {"dziala": True, "adres": ADRES_BACKENDU, "health": json.loads(odp.read())}
    except urllib.error.HTTPError as exc:  # 503 = API działa, ale np. baza/Redis nie
        try:
            health = json.loads(exc.read())
        except ValueError:
            health = None
        return {"dziala": False, "adres": ADRES_BACKENDU, "kod": exc.code, "health": health}
    except (urllib.error.URLError, OSError, ValueError):
        return {"dziala": False, "adres": ADRES_BACKENDU, "kod": None, "health": None}


WYNIKI.mkdir(exist_ok=True)
app.mount("/pliki", StaticFiles(directory=WYNIKI), name="pliki")


def main() -> int:
    parser = argparse.ArgumentParser(description="Strona pokazowa sprintu 1 (http://localhost:8050).")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--bez-przegladarki", action="store_true", help="nie otwieraj strony automatycznie")
    args = parser.parse_args()

    import uvicorn

    adres = f"http://localhost:{args.port}"
    print(f"Strona pokazowa: {adres}   (zatrzymanie: Ctrl+C)")
    if not args.bez_przegladarki:
        threading.Timer(1.5, webbrowser.open, args=(adres,)).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
