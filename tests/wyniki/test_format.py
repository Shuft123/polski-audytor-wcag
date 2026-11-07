import json

import pytest

from audytor.wyniki import Problem, WynikStrony, wczytaj_wynik, zapisz_wynik
from audytor.wyniki.format import MAX_FRAGMENT_HTML


def _problem(**zmiany):
    dane = dict(
        url_podstrony="https://p.pl/",
        zrodlo="axe",
        regula="image-alt",
        kryteria_wcag=["1.1.1"],
        status="blad",
        selektor="img",
        waga="krytyczna",
        poziom_wcag="A",
        wykryto="2026-11-07T12:00:00+00:00",
    )
    dane.update(zmiany)
    return Problem(**dane)


def test_id_is_stable_and_depends_on_element():
    assert _problem().id == _problem(opis="inny opis").id      # te same: url, źródło, reguła, selektor
    assert _problem().id != _problem(selektor="img.logo").id
    assert _problem().id != _problem(zrodlo="ai").id
    assert len(_problem().id) == 16


def test_explicit_id_is_kept():
    assert _problem(id="abc").id == "abc"


@pytest.mark.parametrize(
    "pole, wartosc",
    [
        ("zrodlo", "lighthouse"),
        ("status", "do weryfikacji"),       # ze spacją – niezgodne z kontraktem
        ("waga", "critical"),               # wartość axe, nie nasza
        ("poziom_wcag", "AAAA"),
        ("kryteria_wcag", ["111"]),
        ("kryteria_wcag", ["5.1.1"]),
        ("poziom_pewnosci", 1.5),
    ],
)
def test_invalid_values_are_rejected(pole, wartosc):
    with pytest.raises(ValueError):
        _problem(**{pole: wartosc})


def test_long_html_is_truncated():
    problem = _problem(fragment_html="<div>" + "x" * 5000 + "</div>")
    assert len(problem.fragment_html) == MAX_FRAGMENT_HTML
    assert problem.fragment_html.endswith("…")


def test_summary_counts():
    wynik = WynikStrony(
        url="https://p.pl/",
        requested_url="https://p.pl",
        sprawdzono="2026-11-07T12:00:00+00:00",
        problemy=[
            _problem(),
            _problem(selektor="a", regula="link-name", waga="powazna"),
            _problem(selektor="b", zrodlo="ai", regula="ai-alt-tekst", status="do_weryfikacji",
                     waga="powazna", poziom_pewnosci=0.7),
            _problem(selektor="c", status="odrzucony", waga="drobna"),
        ],
    )
    p = wynik.podsumowanie()
    assert p["liczba_problemow"] == 4
    assert p["wg_statusu"] == {"blad": 2, "do_weryfikacji": 1, "odrzucony": 1}
    assert p["wg_wagi"] == {"krytyczna": 1, "powazna": 2, "umiarkowana": 0, "drobna": 0}  # odrzucone pominięte
    assert p["wg_zrodla"] == {"axe": 3, "ai": 1}


def test_save_and_load_roundtrip(tmp_path):
    wynik = WynikStrony(
        url="https://p.pl/",
        requested_url="https://p.pl",
        sprawdzono="2026-11-07T12:00:00+00:00",
        problemy=[_problem(opis="Obrazy muszą mieć tekst alternatywny.")],
        narzedzia={"axe-core": "4.12.1"},
        migawka="p-pl",
        http_status=200,
        ostrzezenia=["uwaga"],
    )
    plik = zapisz_wynik(wynik, tmp_path / "p-pl")
    dane = json.loads(plik.read_text(encoding="utf-8"))
    assert dane["schema_version"] == "1.0"
    assert "Obrazy muszą" in plik.read_text(encoding="utf-8")   # polskie znaki bez ą
    assert wczytaj_wynik(tmp_path / "p-pl").to_dict() == wynik.to_dict()


def test_load_rejects_other_major_version(tmp_path):
    (tmp_path / "wynik.json").write_text(
        json.dumps({"schema_version": "2.0", "url": "u", "requested_url": "u", "sprawdzono": "t"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="wersja"):
        wczytaj_wynik(tmp_path)
