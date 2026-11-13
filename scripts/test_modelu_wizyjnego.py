"""Test modelu wizyjnego na 10 zrzutach z migawek zespołu (osoba 4, sprint 1).

Zrzuty: dla każdej z 5 migawek w tests/data/snapshots
  * pierwszy ekran strony (1366x768, wycięty z screenshot.jpg) – po zamknięciu banera cookies,
  * screenshot-baner.jpg – ten sam ekran z banerem cookies.

Na każdym zrzucie model dostaje 3 zadania (prompty po polsku, odpowiedź w JSON):
  opis    – opis zrzutu po polsku (sprawdza rozumienie obrazu i polszczyznę; podstawa pod `obraz_opis` w F9),
  tekst   – teksty wtopione w obrazy/grafiki i ocena ich czytelności (prototyp F13, kontrast na obrazach),
  baner   – czy widać baner cookies i czy ma przycisk odrzucenia (wynik da się sprawdzić automatycznie z meta.json).

Działa z dowolnym API zgodnym z OpenAI (Ollama, vLLM, LM Studio, OpenRouter, Gemini…):

    # lokalnie przez Ollamę
    ollama pull qwen2.5vl:3b
    python scripts/test_modelu_wizyjnego.py --model qwen2.5vl:3b

    # model w chmurze (klucz w zmiennej środowiskowej AUDYTOR_API_KEY)
    python scripts/test_modelu_wizyjnego.py --base-url https://openrouter.ai/api/v1 --model <nazwa>

Wynik: wyniki/wizja/<model>.csv (jeden wiersz na zrzut i zadanie) + <model>.json z surowymi odpowiedziami.
Kolumnę `ocena_reczna` uzupełnia człowiek (1 = poprawnie, 0 = źle) – z niej liczymy trafność opisu i tekstu.
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

KATALOG_MIGAWEK = Path("tests/data/snapshots")
WYJSCIE = Path("wyniki/wizja")

SYSTEM = (
    "Jesteś asystentem audytora dostępności cyfrowej (WCAG 2.1). Oceniasz zrzuty ekranu polskich stron "
    "internetowych. Odpowiadasz wyłącznie poprawnym JSON-em, bez komentarzy i bez bloku ```."
)

ZADANIA = {
    "opis": (
        "Opisz ten zrzut ekranu strony internetowej po polsku w 1–2 zdaniach: czyja to strona i co "
        "jest na niej najważniejsze. Zwróć JSON: {\"opis\": \"...\", \"typ_strony\": \"urząd|uczelnia|sklep|inna\"}"
    ),
    "tekst": (
        "Znajdź na zrzucie teksty, które są częścią obrazów lub grafik (banery, plakaty, zdjęcia z napisami), "
        "a NIE zwykłym tekstem strony. Dla każdego oceń, czy jest łatwy do przeczytania (kontrast z tłem). "
        "Zwróć JSON: {\"teksty_na_obrazach\": [{\"tekst\": \"...\", \"czytelny\": true, "
        "\"problem\": \"np. jasny tekst na jasnym zdjęciu albo pusty napis\"}]}. Gdy brak – pusta lista."
    ),
    "baner": (
        "Czy na zrzucie widać baner lub okno zgody na pliki cookies? Jeśli tak, czy ma przycisk odrzucenia "
        "(np. „Odrzuć”, „Tylko niezbędne”)? Zwróć JSON: {\"baner_cookies\": true, \"przycisk_odrzucenia\": true, "
        "\"napisy_przyciskow\": [\"...\"]}"
    ),
}


def zrzuty() -> list[dict]:
    """10 zrzutów testowych + oczekiwana odpowiedź dla zadania `baner` (z meta.json)."""
    lista = []
    for folder in sorted(p for p in KATALOG_MIGAWEK.iterdir() if (p / "meta.json").exists()):
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        pliki, baner = meta["files"], meta.get("cookie_banner", {})
        pelny = Image.open(folder / pliki["screenshot"]).convert("RGB")
        vp = meta.get("viewport", {"width": 1366, "height": 768})
        lista.append({
            "id": f"{folder.name}/ekran",
            "obraz": pelny.crop((0, 0, vp["width"], min(vp["height"], pelny.height))),
            # baner zostaje na stronie tylko gdy nie dało się go zamknąć (np. wasilkow.pl)
            "oczekiwany_baner": bool(baner.get("detected") and not baner.get("dismissed")),
        })
        if "cookie_banner_screenshot" in pliki:
            lista.append({
                "id": f"{folder.name}/baner",
                "obraz": Image.open(folder / pliki["cookie_banner_screenshot"]).convert("RGB"),
                "oczekiwany_baner": True,
            })
    return lista


def jako_data_url(obraz: Image.Image) -> str:
    bufor = io.BytesIO()
    obraz.save(bufor, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(bufor.getvalue()).decode()


def zapytaj(base_url: str, model: str, klucz: str | None, obraz_url: str, polecenie: str, timeout: float) -> tuple[str, dict]:
    tresc = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": polecenie},
                {"type": "image_url", "image_url": {"url": obraz_url}},
            ]},
        ],
    }
    zadanie = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(tresc).encode(),
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {klucz}"} if klucz else {})},
    )
    with urllib.request.urlopen(zadanie, timeout=timeout) as odp:
        dane = json.load(odp)
    return dane["choices"][0]["message"]["content"], dane.get("usage", {})


def zapytaj_ollama(base_url: str, model: str, obraz_url: str, polecenie: str, timeout: float,
                   opcje: dict) -> tuple[str, dict]:
    """Natywne API Ollamy (/api/chat) – pozwala przekazać opcje, np. {"num_gpu": 0} (tylko CPU)."""
    tresc = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0.1, **opcje},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": polecenie, "images": [obraz_url.split(",", 1)[1]]},
        ],
    }
    adres = re.sub(r"/v1/?$", "", base_url.rstrip("/")) + "/api/chat"
    zadanie = urllib.request.Request(adres, data=json.dumps(tresc).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(zadanie, timeout=timeout) as odp:
        dane = json.load(odp)
    uzycie = {"total_tokens": dane.get("prompt_eval_count", 0) + dane.get("eval_count", 0)}
    return dane["message"]["content"], uzycie


def parsuj_json(tekst: str) -> dict | None:
    tekst = re.sub(r"^```(?:json)?|```$", "", tekst.strip(), flags=re.MULTILINE).strip()
    try:
        wynik = json.loads(tekst)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", tekst, flags=re.DOTALL)
        if not m:
            return None
        try:
            wynik = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return wynik if isinstance(wynik, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--model", required=True, help="nazwa modelu, np. qwen2.5vl:3b")
    parser.add_argument("--base-url", default="http://localhost:11434/v1", help="API zgodne z OpenAI (domyślnie Ollama)")
    parser.add_argument("--zadania", default=",".join(ZADANIA), help="lista zadań, domyślnie wszystkie")
    parser.add_argument("--timeout", type=float, default=300, help="limit na jedno zapytanie w sekundach")
    parser.add_argument("--ollama-opcje", type=json.loads, default=None,
                        help='użyj natywnego API Ollamy z opcjami, np. \'{"num_gpu": 0}\' = tylko CPU')
    parser.add_argument("--cpu", action="store_true",
                        help="Ollama liczy tylko na CPU (gdy model na GPU zwraca śmieci, np. RTX 20xx); dodaje sufiks _cpu")
    parser.add_argument("--sufiks", default="", help="dopisek do nazwy pliku wyników, np. _cpu")
    args = parser.parse_args(argv)
    if args.cpu:
        args.ollama_opcje = {**(args.ollama_opcje or {}), "num_gpu": 0}
        args.sufiks = args.sufiks or "_cpu"

    klucz = os.environ.get("AUDYTOR_API_KEY")
    zadania = [z.strip() for z in args.zadania.split(",") if z.strip()]
    nieznane = set(zadania) - set(ZADANIA)
    if nieznane:
        parser.error(f"nieznane zadania: {', '.join(sorted(nieznane))}")

    WYJSCIE.mkdir(parents=True, exist_ok=True)
    nazwa = re.sub(r"[^A-Za-z0-9._-]+", "_", args.model) + args.sufiks
    wiersze, surowe = [], []
    for zrzut in zrzuty():
        obraz_url = jako_data_url(zrzut["obraz"])
        for zadanie in zadania:
            start = time.monotonic()
            try:
                if args.ollama_opcje is not None:
                    odpowiedz, uzycie = zapytaj_ollama(args.base_url, args.model, obraz_url, ZADANIA[zadanie],
                                                       args.timeout, args.ollama_opcje)
                else:
                    odpowiedz, uzycie = zapytaj(args.base_url, args.model, klucz, obraz_url, ZADANIA[zadanie], args.timeout)
                blad = ""
            except urllib.error.HTTPError as exc:
                tresc_bledu = exc.read().decode(errors="replace")[:200]
                odpowiedz, uzycie, blad = "", {}, f"HTTP {exc.code}: {tresc_bledu}"
            except (urllib.error.URLError, TimeoutError, KeyError) as exc:
                odpowiedz, uzycie, blad = "", {}, str(exc)
            czas = time.monotonic() - start
            dane = parsuj_json(odpowiedz) if odpowiedz else None

            zgodny = ""
            if zadanie == "baner" and dane is not None and "baner_cookies" in dane:
                zgodny = int(bool(dane["baner_cookies"]) == zrzut["oczekiwany_baner"])

            wiersze.append({
                "zrzut": zrzut["id"], "zadanie": zadanie, "czas_s": round(czas, 1),
                "poprawny_json": int(dane is not None), "zgodny_z_meta": zgodny,
                "tokeny": uzycie.get("total_tokens", ""), "blad": blad,
                "odpowiedz": json.dumps(dane, ensure_ascii=False) if dane is not None else odpowiedz[:500],
                "ocena_reczna": "",
            })
            surowe.append({"zrzut": zrzut["id"], "zadanie": zadanie, "odpowiedz": odpowiedz, "czas_s": czas})
            print(f"{zrzut['id']:<22} {zadanie:<6} {czas:6.1f}s  json={'tak' if dane else 'NIE'}"
                  f"{'  zgodny=' + str(zgodny) if zgodny != '' else ''}{'  BŁĄD: ' + blad if blad else ''}")

    with open(WYJSCIE / f"{nazwa}.csv", "w", newline="", encoding="utf-8-sig") as f:
        pisz = csv.DictWriter(f, fieldnames=list(wiersze[0]))
        pisz.writeheader()
        pisz.writerows(wiersze)
    (WYJSCIE / f"{nazwa}.json").write_text(json.dumps(surowe, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = [w for w in wiersze if not w["blad"]]
    banery = [w for w in ok if w["zgodny_z_meta"] != ""]
    print(f"\nModel {args.model}: {len(ok)}/{len(wiersze)} odpowiedzi, "
          f"poprawny JSON {sum(w['poprawny_json'] for w in ok)}/{len(ok)}, "
          f"baner cookies zgodny z meta.json {sum(w['zgodny_z_meta'] for w in banery)}/{len(banery)}, "
          f"średni czas {sum(w['czas_s'] for w in ok) / max(1, len(ok)):.1f} s")
    print(f"Wyniki: {WYJSCIE / (nazwa + '.csv')}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
