"""Pomiar widoczności fokusu (WCAG 2.4.7) na podstawie dwóch wycinków zrzutu ekranu.

Pomysł: ten sam fragment ekranu wokół elementu fotografujemy dwa razy – z fokusem i bez
fokusu (po `blur()`). Wskaźnik fokusu to piksele, które zmieniły się między zrzutami.
Liczymy, ile z nich zmieniło kolor z kontrastem co najmniej 3:1 (próg z WCAG 2.2, kryterium
2.4.11/2.4.13 – dla 2.4.7 w WCAG 2.1 nie ma liczbowego progu, więc bierzemy go stamtąd)
i porównujemy z obwodem elementu. Wskaźnik ≈ 1,0 oznacza mniej więcej jednopikselową,
kontrastową ramkę dookoła elementu.

Moduł nie zależy od przeglądarki – działa na obrazach PIL, więc da się go testować bez Chromium.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from PIL import Image, ImageChops

# Różnica kanału (0–255), poniżej której piksel uznajemy za niezmieniony (antyaliasing, szum).
PROG_ZMIANY = 24
# Minimalny kontrast między kolorem piksela bez fokusu i z fokusem.
PROG_KONTRASTU = 3.0
# Wskaźnik (kontrastowe piksele / obwód elementu), od którego fokus uznajemy za widoczny.
PROG_WSKAZNIKA = 1.0


def luminancja(rgb: tuple[int, int, int]) -> float:
    """Względna luminancja koloru sRGB wg definicji WCAG."""

    def kanal(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb[:3]
    return 0.2126 * kanal(r) + 0.7152 * kanal(g) + 0.0722 * kanal(b)


def kontrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """Współczynnik kontrastu WCAG (1–21) między dwoma kolorami."""
    la, lb = luminancja(a), luminancja(b)
    jasny, ciemny = max(la, lb), min(la, lb)
    return (jasny + 0.05) / (ciemny + 0.05)


@dataclass
class PomiarFokusu:
    zmienione_px: int          # piksele, które zmieniły się po nadaniu fokusu
    kontrastowe_px: int        # z nich: zmiana koloru o kontraście >= PROG_KONTRASTU
    obwod_px: int              # obwód elementu (2 * (szerokość + wysokość))
    wskaznik: float            # kontrastowe_px / obwod_px
    max_kontrast: float        # największy kontrast zmiany (1.0 = brak zmiany)

    @property
    def brak_zmiany(self) -> bool:
        return self.zmienione_px == 0

    @property
    def widoczny(self) -> bool:
        return self.wskaznik >= PROG_WSKAZNIKA

    def to_dict(self) -> dict:
        dane = asdict(self)
        dane["wskaznik"] = round(self.wskaznik, 3)
        dane["max_kontrast"] = round(self.max_kontrast, 2)
        return dane


def zmierz(bez_fokusu: Image.Image, z_fokusem: Image.Image, szerokosc: float, wysokosc: float) -> PomiarFokusu:
    """Porównuje dwa wycinki tego samego obszaru (bez i z fokusem)."""
    if bez_fokusu.size != z_fokusem.size:
        raise ValueError(f"Różne rozmiary wycinków: {bez_fokusu.size} vs {z_fokusem.size}")
    a = bez_fokusu.convert("RGB")
    b = z_fokusem.convert("RGB")

    # Szybki filtr: maksymalna różnica kanałów w każdym pikselu.
    roznica = ImageChops.difference(a, b)
    r, g, bl = roznica.split()
    maks = ImageChops.lighter(ImageChops.lighter(r, g), bl)
    maska = maks.point(lambda v: 255 if v > PROG_ZMIANY else 0)

    zmienione = 0
    kontrastowe = 0
    max_k = 1.0
    px_a, px_b, px_m = a.load(), b.load(), maska.load()
    obszar = maska.getbbox() or (0, 0, 0, 0)   # przeglądamy tylko prostokąt ze zmianami
    cache: dict[tuple, float] = {}
    for y in range(obszar[1], obszar[3]):
        for x in range(obszar[0], obszar[2]):
            if not px_m[x, y]:
                continue
            zmienione += 1
            para = (px_a[x, y], px_b[x, y])
            k = cache.get(para)
            if k is None:
                k = cache[para] = kontrast(*para)
            if k >= PROG_KONTRASTU:
                kontrastowe += 1
            if k > max_k:
                max_k = k

    obwod = max(1, round(2 * (szerokosc + wysokosc)))
    return PomiarFokusu(
        zmienione_px=zmienione,
        kontrastowe_px=kontrastowe,
        obwod_px=obwod,
        wskaznik=kontrastowe / obwod,
        max_kontrast=max_k,
    )


def obraz_porownania(bez_fokusu: Image.Image, z_fokusem: Image.Image) -> Image.Image:
    """Obraz do raportu/demo: [bez fokusu | z fokusem | zmienione piksele na czerwono]."""
    a = bez_fokusu.convert("RGB")
    b = z_fokusem.convert("RGB")
    roznica = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > PROG_ZMIANY // 2 else 0)
    zmiany = Image.blend(a, Image.new("RGB", a.size, (255, 255, 255)), 0.75)
    zmiany.paste(Image.new("RGB", a.size, (220, 0, 0)), mask=roznica)

    odstep = 6
    wynik = Image.new("RGB", (a.width * 3 + odstep * 2, a.height), (128, 128, 128))
    for i, obraz in enumerate((a, b, zmiany)):
        wynik.paste(obraz, (i * (a.width + odstep), 0))
    return wynik
