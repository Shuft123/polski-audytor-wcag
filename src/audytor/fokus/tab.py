"""Przechodzenie po stronie klawiszem Tab i ocena widoczności fokusu (F8, WCAG 2.4.7).

Dla każdego kroku:
1. naciskamy Tab i odczytujemy aktywny element (selektor, rola, nazwa, położenie, styl fokusu),
2. robimy zrzut obszaru wokół elementu Z fokusem,
3. zdejmujemy fokus (`blur()`), robimy zrzut tego samego obszaru BEZ fokusu i oddajemy fokus,
4. porównujemy zrzuty (`pomiar.zmierz`) i wystawiamy werdykt.

Działa na żywej stronie z crawlera (`Renderer.open`), patrz docs/ai-wizja-fokus.md.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from playwright.sync_api import Page

from .pomiar import PomiarFokusu, obraz_porownania, zmierz

# Margines wokół elementu w zrzutach (px) – obwódka fokusu bywa rysowana na zewnątrz elementu.
MARGINES = 10
# Po tylu kolejnych Tabach na tym samym elemencie uznajemy, że to pułapka klawiaturowa (2.1.2).
LIMIT_PULAPKI = 3
MAX_FRAGMENT_HTML = 2000

# Ustawia punkt startowy nawigacji sekwencyjnej na początek dokumentu: crawler mógł kliknąć
# przycisk banera cookies, a wtedy pierwszy Tab poszedłby od banera, a nie od góry strony.
_JS_START = """
() => {
  window.scrollTo(0, 0);
  if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur();
  const body = document.body;
  if (!body) return;
  const mialTabindex = body.hasAttribute('tabindex');
  if (!mialTabindex) body.setAttribute('tabindex', '-1');
  body.focus({preventScroll: true});
  if (!mialTabindex) body.removeAttribute('tabindex');
}
"""

# Opis aktywnego elementu. Zapamiętuje go w window.__audytorFokus, żeby móc zdjąć i oddać fokus.
_JS_AKTYWNY = """
() => {
  let el = document.activeElement;
  while (el && el.shadowRoot && el.shadowRoot.activeElement) el = el.shadowRoot.activeElement;
  if (!el || el === document.body || el === document.documentElement) return null;
  window.__audytorFokus = el;

  const selektor = (node) => {
    if (node.id && document.querySelectorAll('#' + CSS.escape(node.id)).length === 1)
      return '#' + CSS.escape(node.id);
    const czesci = [];
    while (node && node.nodeType === 1 && node !== document.documentElement) {
      if (node.id && document.querySelectorAll('#' + CSS.escape(node.id)).length === 1) {
        czesci.unshift('#' + CSS.escape(node.id));
        break;
      }
      let czesc = node.localName;
      const rodzic = node.parentElement;
      if (rodzic) {
        const tegoTypu = [...rodzic.children].filter(c => c.localName === node.localName);
        if (tegoTypu.length > 1) czesc += ':nth-of-type(' + (tegoTypu.indexOf(node) + 1) + ')';
      }
      czesci.unshift(czesc);
      node = rodzic;
    }
    return czesci.join(' > ');
  };

  const r = el.getBoundingClientRect();
  const s = getComputedStyle(el);
  const tekst = (el.innerText || el.value || el.alt || '').replace(/\\s+/g, ' ').trim();
  const nazwa = el.getAttribute('aria-label') || tekst || el.getAttribute('title') || '';
  const widoczny = r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'
    && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
  let fv = null;
  try { fv = el.matches(':focus-visible'); } catch (e) {}
  return {
    selektor: selektor(el),
    tag: el.localName,
    rola: el.getAttribute('role') || '',
    nazwa: nazwa.slice(0, 120),
    fragment_html: el.outerHTML.slice(0, 2000),
    rect: {x: r.x, y: r.y, width: r.width, height: r.height},
    scroll: {x: scrollX, y: scrollY},
    viewport: {width: innerWidth, height: innerHeight},
    widoczny: widoczny,
    focus_visible: fv,
    styl: {
      outline: s.outlineStyle + ' ' + s.outlineWidth + ' ' + s.outlineColor,
      outline_offset: s.outlineOffset,
      box_shadow: s.boxShadow,
      border: s.borderTopStyle + ' ' + s.borderTopWidth + ' ' + s.borderTopColor,
      background: s.backgroundColor,
    },
  };
}
"""

_JS_PRZEWIN = "() => window.__audytorFokus && window.__audytorFokus.scrollIntoView({block: 'nearest', inline: 'nearest'})"
_JS_BLUR = "() => window.__audytorFokus && window.__audytorFokus.blur()"
_JS_FOCUS = "() => window.__audytorFokus && window.__audytorFokus.focus({preventScroll: true})"
_JS_WYSOKOSC = "() => Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)"


@dataclass
class KrokFokusu:
    nr: int
    selektor: str
    tag: str
    rola: str
    nazwa: str
    fragment_html: str
    rect_strony: dict[str, float]      # położenie na całej stronie (do mapy fokusu)
    widoczny: bool
    focus_visible: bool | None
    styl: dict[str, str]
    pomiar: PomiarFokusu | None = None
    werdykt: str = ""                  # ok | slaby | brak | niewidoczny | zgubiony
    plik_porownania: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "nr": self.nr,
            "selektor": self.selektor,
            "tag": self.tag,
            "rola": self.rola,
            "nazwa": self.nazwa,
            "rect_strony": self.rect_strony,
            "widoczny": self.widoczny,
            "focus_visible": self.focus_visible,
            "styl": self.styl,
            "pomiar": self.pomiar.to_dict() if self.pomiar else None,
            "werdykt": self.werdykt,
            "plik_porownania": self.plik_porownania,
        }


@dataclass
class WynikFokusu:
    url: str
    kroki: list[KrokFokusu] = field(default_factory=list)
    zakonczenie: str = ""              # dlaczego przestaliśmy naciskać Tab
    problemy: list[dict[str, Any]] = field(default_factory=list)
    ostrzezenia: list[str] = field(default_factory=list)
    sprawdzono: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def podsumowanie(self) -> dict[str, int]:
        licznik = {"kroki": len(self.kroki), "ok": 0, "slaby": 0, "brak": 0, "niewidoczny": 0, "zgubiony": 0}
        for krok in self.kroki:
            licznik[krok.werdykt] = licznik.get(krok.werdykt, 0) + 1
        return licznik

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "sprawdzono": self.sprawdzono,
            "zakonczenie": self.zakonczenie,
            "podsumowanie": self.podsumowanie(),
            "ostrzezenia": self.ostrzezenia,
            "problemy": self.problemy,
            "kroki": [k.to_dict() for k in self.kroki],
        }


def _werdykt(widoczny: bool, pomiar: PomiarFokusu | None) -> str:
    if not widoczny or pomiar is None:
        return "niewidoczny"
    if pomiar.brak_zmiany:
        return "brak"
    return "ok" if pomiar.widoczny else "slaby"


def _id_problemu(url: str, regula: str, selektor: str) -> str:
    # Ten sam sposób liczenia co identyfikator_problemu() w audytor.wyniki (F7).
    klucz = "\x1f".join([url, "ai", regula, selektor])
    return hashlib.sha1(klucz.encode("utf-8")).hexdigest()[:16]


def _problem(url: str, krok: KrokFokusu, regula: str, kryterium: str, waga: str,
             pewnosc: float, opis: str, szczegoly: str) -> dict[str, Any]:
    """Problem w formacie wspólnego modelu wyniku (audytor.wyniki.Problem, F7)."""
    return {
        "url_podstrony": url,
        "zrodlo": "ai",
        "regula": regula,
        "kryteria_wcag": [kryterium],
        "status": "do_weryfikacji",
        "selektor": krok.selektor,
        "fragment_html": krok.fragment_html[:MAX_FRAGMENT_HTML],
        "waga": waga,
        "poziom_wcag": "A" if kryterium == "2.1.2" else "AA",
        "opis": opis,
        "szczegoly": szczegoly,
        "link_pomocy": f"https://www.w3.org/WAI/WCAG21/Understanding/{'no-keyboard-trap' if kryterium == '2.1.2' else 'focus-visible'}",
        "poziom_pewnosci": pewnosc,
        "uzasadnienie": None,
        "wykryto": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "id": _id_problemu(url, regula, krok.selektor),
    }


def _problemy_kroku(url: str, krok: KrokFokusu) -> list[dict[str, Any]]:
    p = krok.pomiar
    if krok.werdykt == "brak":
        return [_problem(
            url, krok, "fokus-niewidoczny", "2.4.7", "powazna", 0.9,
            "Brak widocznego wskaźnika fokusu",
            f"Po przejściu klawiszem Tab na element <{krok.tag}> „{krok.nazwa}” wygląd strony w jego "
            f"otoczeniu ({MARGINES} px) się nie zmienia. Dodaj np. `:focus-visible {{ outline: 2px solid; }}`.",
        )]
    if krok.werdykt == "slaby" and p is not None:
        return [_problem(
            url, krok, "fokus-slabo-widoczny", "2.4.7", "umiarkowana", 0.6,
            "Wskaźnik fokusu może być słabo widoczny",
            f"Zmiana po nadaniu fokusu jest mała lub mało kontrastowa: {p.kontrastowe_px} px o kontraście "
            f"≥ 3:1 przy obwodzie elementu {p.obwod_px} px (wskaźnik {p.wskaznik:.2f}, "
            f"maks. kontrast zmiany {p.max_kontrast:.1f}:1).",
        )]
    if krok.werdykt == "niewidoczny":
        return [_problem(
            url, krok, "fokus-poza-ekranem", "2.4.7", "umiarkowana", 0.5,
            "Fokus trafia na element niewidoczny na ekranie",
            "Element dostaje fokus, ale ma zerowy rozmiar lub leży poza widokiem. Użytkownik klawiatury "
            "nie widzi, gdzie jest. (Wyjątek: link „przejdź do treści”, który pojawia się dopiero po fokusie.)",
        )]
    return []


def _dodaj_zgubiony(wynik: WynikFokusu, url: str) -> None:
    """Tab z poprzedniego elementu przeniósł fokus „donikąd” (na <body>), a kolejny Tab wrócił na stronę."""
    poprzedni = wynik.kroki[-1]
    krok = KrokFokusu(
        nr=len(wynik.kroki) + 1, selektor="body", tag="body", rola="", nazwa="(fokus poza elementami strony)",
        fragment_html="", rect_strony={"x": 0, "y": 0, "width": 0, "height": 0}, widoczny=False,
        focus_visible=None, styl={}, werdykt="zgubiony",
    )
    wynik.kroki.append(krok)
    wynik.problemy.append(_problem(
        url, poprzedni, "fokus-zgubiony", "2.4.7", "powazna", 0.7,
        "Fokus znika po przejściu z tego elementu",
        f"Tab z elementu <{poprzedni.tag}> „{poprzedni.nazwa}” przenosi fokus poza widoczne elementy strony "
        "(najczęściej do ukrytego podmenu lub usuniętego elementu). Użytkownik klawiatury traci orientację.",
    ))


def _wycinek(page: Page, info: dict[str, Any]) -> dict[str, float] | None:
    """Prostokąt zrzutu: element + margines, przycięty do okna."""
    r, vp = info["rect"], info["viewport"]
    x0 = max(0.0, r["x"] - MARGINES)
    y0 = max(0.0, r["y"] - MARGINES)
    x1 = min(float(vp["width"]), r["x"] + r["width"] + MARGINES)
    y1 = min(float(vp["height"]), r["y"] + r["height"] + MARGINES)
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def _zrzut(page: Page, clip: dict[str, float]) -> Image.Image:
    png = page.screenshot(clip=clip, animations="disabled", caret="hide")
    return Image.open(io.BytesIO(png)).convert("RGB")


def przejdz_tabem(page: Page, url: str | None = None, max_krokow: int = 60,
                  folder_zrzutow: str | Path | None = None, pauza_ms: int = 150) -> WynikFokusu:
    """Naciska Tab do `max_krokow` razy i ocenia widoczność fokusu na każdym elemencie.

    `folder_zrzutow` – jeśli podany, zapisuje tam obrazy porównania `NN_porownanie.png`.
    """
    url = url or page.url
    wynik = WynikFokusu(url=url)
    folder = Path(folder_zrzutow) if folder_zrzutow else None
    if folder:
        folder.mkdir(parents=True, exist_ok=True)

    page.mouse.move(0, 0)          # kursor nad elementem dałby efekt :hover na zrzutach
    page.evaluate(_JS_START)

    pierwszy: str | None = None
    poprzedni: str | None = None
    powtorzenia = 0
    na_body = 0     # ile kolejnych Tabów skończyło się fokusem na <body> (poza elementami strony)
    for nr in range(1, max_krokow + 1):
        page.keyboard.press("Tab")
        page.wait_for_timeout(pauza_ms)
        info = page.evaluate(_JS_AKTYWNY)
        if info is None:
            # Jedno „wyjście” na <body> to albo koniec strony (fokus idzie do paska przeglądarki),
            # albo zgubiony fokus (np. ukryte podmenu). Rozstrzyga następny Tab.
            na_body += 1
            if na_body >= 2 or not wynik.kroki:
                wynik.zakonczenie = "fokus opuścił stronę (koniec kolejności Tab)"
                break
            continue
        if info["selektor"] == pierwszy:
            wynik.zakonczenie = "fokus wrócił do pierwszego elementu (pełny cykl)"
            break
        if na_body and wynik.kroki:
            _dodaj_zgubiony(wynik, url)
        na_body = 0
        if info["selektor"] == poprzedni:
            powtorzenia += 1
            if powtorzenia >= LIMIT_PULAPKI - 1:
                wynik.zakonczenie = "fokus utknął na jednym elemencie (możliwa pułapka klawiaturowa)"
                ostatni = wynik.kroki[-1]
                wynik.problemy.append(_problem(
                    url, ostatni, "fokus-pulapka", "2.1.2", "krytyczna", 0.7,
                    "Możliwa pułapka klawiaturowa",
                    f"{LIMIT_PULAPKI} kolejne naciśnięcia Tab zostawiają fokus na tym samym elemencie.",
                ))
                break
            continue
        powtorzenia = 0
        poprzedni = info["selektor"]
        pierwszy = pierwszy or info["selektor"]

        if info["widoczny"]:
            page.evaluate(_JS_PRZEWIN)
            info = page.evaluate(_JS_AKTYWNY) or info

        r, sc = info["rect"], info["scroll"]
        krok = KrokFokusu(
            nr=len(wynik.kroki) + 1,
            selektor=info["selektor"],
            tag=info["tag"],
            rola=info["rola"],
            nazwa=info["nazwa"],
            fragment_html=info["fragment_html"],
            rect_strony={"x": r["x"] + sc["x"], "y": r["y"] + sc["y"], "width": r["width"], "height": r["height"]},
            widoczny=bool(info["widoczny"]),
            focus_visible=info["focus_visible"],
            styl=info["styl"],
        )

        clip = _wycinek(page, info) if krok.widoczny else None
        if clip is not None:
            z_fokusem = _zrzut(page, clip)
            page.evaluate(_JS_BLUR)
            page.wait_for_timeout(pauza_ms)
            bez_fokusu = _zrzut(page, clip)
            page.evaluate(_JS_FOCUS)
            krok.pomiar = zmierz(bez_fokusu, z_fokusem, r["width"], r["height"])
            if folder:
                nazwa_pliku = f"{krok.nr:02d}_porownanie.png"
                obraz_porownania(bez_fokusu, z_fokusem).save(folder / nazwa_pliku)
                krok.plik_porownania = nazwa_pliku

        krok.werdykt = _werdykt(krok.widoczny, krok.pomiar)
        wynik.kroki.append(krok)
        wynik.problemy.extend(_problemy_kroku(url, krok))
    else:
        wynik.zakonczenie = f"osiągnięto limit {max_krokow} kroków"
        wynik.ostrzezenia.append(f"Sprawdzono tylko pierwsze {max_krokow} elementów – zwiększ --max-krokow")

    return wynik


_KOLORY = {"ok": (0, 140, 60), "slaby": (230, 140, 0), "brak": (210, 0, 0), "niewidoczny": (120, 0, 200), "zgubiony": (0, 0, 0)}


def mapa_fokusu(page: Page, wynik: WynikFokusu, max_wysokosc: int = 15_000) -> Image.Image:
    """Zrzut całej strony z ponumerowanymi ramkami w kolejności Tab (kolor = werdykt).

    Przydaje się też do oceny kolejności fokusu (2.4.3) przez człowieka lub model wizyjny.
    """
    page.evaluate(_JS_BLUR)
    page.evaluate("() => window.scrollTo(0, 0)")
    wysokosc = page.evaluate(_JS_WYSOKOSC)
    kwargs: dict[str, Any] = {"full_page": True, "animations": "disabled", "caret": "hide"}
    if wysokosc > max_wysokosc:
        kwargs["clip"] = {"x": 0, "y": 0, "width": page.viewport_size["width"], "height": max_wysokosc}
    obraz = Image.open(io.BytesIO(page.screenshot(**kwargs))).convert("RGB")

    rysuj = ImageDraw.Draw(obraz)
    for krok in wynik.kroki:
        r = krok.rect_strony
        if r["width"] <= 0 or r["height"] <= 0:
            continue
        kolor = _KOLORY.get(krok.werdykt, (0, 0, 0))
        x0, y0 = r["x"] - 2, r["y"] - 2
        rysuj.rectangle([x0, y0, r["x"] + r["width"] + 2, r["y"] + r["height"] + 2], outline=kolor, width=3)
        etykieta = str(krok.nr)
        tw = 8 * len(etykieta) + 6
        rysuj.rectangle([x0, y0 - 16, x0 + tw, y0], fill=kolor)
        rysuj.text((x0 + 3, y0 - 15), etykieta, fill=(255, 255, 255))
    return obraz
