"""Pomiar widoczności fokusu na sztucznych obrazach – bez przeglądarki."""

import pytest
from PIL import Image, ImageDraw

from audytor.fokus.pomiar import kontrast, obraz_porownania, zmierz

BIALY = (255, 255, 255)


def _przycisk(obwodka: tuple[int, int, int] | None = None, tlo=BIALY) -> Image.Image:
    """Wycinek 120x50: przycisk 100x30 z marginesem 10 px, opcjonalnie z obwódką 2 px."""
    img = Image.new("RGB", (120, 50), tlo)
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, 109, 39], fill=(230, 230, 230))
    if obwodka:
        d.rectangle([8, 8, 111, 41], outline=obwodka, width=2)
    return img


def test_kontrast_wzorcowe_wartosci():
    assert kontrast((0, 0, 0), BIALY) == pytest.approx(21.0)
    assert kontrast(BIALY, BIALY) == pytest.approx(1.0)
    # #767676 na białym to klasyczna granica 4.5:1
    assert kontrast((0x76, 0x76, 0x76), BIALY) == pytest.approx(4.54, abs=0.01)


def test_brak_zmiany_to_brak_fokusu():
    pomiar = zmierz(_przycisk(), _przycisk(), 100, 30)
    assert pomiar.brak_zmiany
    assert not pomiar.widoczny
    assert pomiar.max_kontrast == 1.0


def test_wyrazna_obwodka_jest_widoczna():
    pomiar = zmierz(_przycisk(), _przycisk(obwodka=(0, 0, 0)), 100, 30)
    assert not pomiar.brak_zmiany
    assert pomiar.widoczny
    assert pomiar.max_kontrast == pytest.approx(21.0)


def test_blada_obwodka_jest_slaba():
    # Jasnoszara obwódka na białym tle: zmiana jest, ale kontrast < 3:1.
    pomiar = zmierz(_przycisk(), _przycisk(obwodka=(200, 200, 200)), 100, 30)
    assert pomiar.zmienione_px > 0
    assert pomiar.kontrastowe_px == 0
    assert not pomiar.widoczny


def test_obwodka_w_kolorze_tla_jest_niewidoczna():
    # Przypadek z pb.edu.pl: obwódka w tym samym kolorze co ciemne tło nagłówka.
    tlo = (0, 73, 75)
    pomiar = zmierz(_przycisk(tlo=tlo), _przycisk(obwodka=tlo, tlo=tlo), 100, 30)
    assert pomiar.brak_zmiany


def test_rozne_rozmiary_to_blad():
    with pytest.raises(ValueError):
        zmierz(Image.new("RGB", (10, 10)), Image.new("RGB", (11, 10)), 5, 5)


def test_obraz_porownania_ma_trzy_panele():
    obraz = obraz_porownania(_przycisk(), _przycisk(obwodka=(0, 0, 0)))
    assert obraz.size == (120 * 3 + 12, 50)
