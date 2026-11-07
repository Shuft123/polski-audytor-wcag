"""Mapowanie wyniku axe-core na wspólny format – bez przeglądarki (działa w CI).

data/axe_wynik_przyklad.json to prawdziwy wynik axe-core 4.12.1 (komunikaty po polsku) dla małej
strony z typowymi błędami: obraz bez alt, pusty link, pole bez etykiety, brak lang, słaby kontrast
oraz tekst na obrazie tła (axe nie umie rozstrzygnąć -> incomplete).
"""

import json
from pathlib import Path

import pytest

from audytor.axe import axe_na_problemy, kryteria_z_tagow, poziom_z_tagow, selektor_z_target

DATA = Path(__file__).parent / "data"
URL = "https://gmina-testowa.pl/"


@pytest.fixture(scope="module")
def wynik_axe():
    return json.loads((DATA / "axe_wynik_przyklad.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def problemy(wynik_axe):
    return {(p.regula, p.status): p for p in axe_na_problemy(wynik_axe, URL)}


@pytest.mark.parametrize(
    "tagi, oczekiwane",
    [
        (["wcag2a", "wcag111", "section508"], ["1.1.1"]),
        (["wcag2a", "wcag244", "wcag412", "EN-9.2.4.4", "RGAA-6.2.1"], ["2.4.4", "4.1.2"]),
        (["wcag21aa", "wcag1410"], ["1.4.10"]),       # dwucyfrowy numer kryterium
        (["wcag2aa", "wcag143", "wcag143"], ["1.4.3"]),  # bez duplikatów
        (["best-practice", "cat.keyboard"], []),
    ],
)
def test_kryteria_z_tagow(tagi, oczekiwane):
    assert kryteria_z_tagow(tagi) == oczekiwane


@pytest.mark.parametrize(
    "tagi, oczekiwany",
    [
        (["wcag2a", "wcag111"], "A"),
        (["wcag21aa", "wcag1410"], "AA"),
        (["wcag2aaa", "wcag146"], "AAA"),
        (["wcag2a", "wcag2aa"], "A"),                 # najniższy poziom wygrywa
        (["best-practice"], None),
    ],
)
def test_poziom_z_tagow(tagi, oczekiwany):
    assert poziom_z_tagow(tagi) == oczekiwany


@pytest.mark.parametrize(
    "target, oczekiwany",
    [
        (["#menu > a"], "#menu > a"),
        ([["moj-komponent", "button"]], "moj-komponent >>> button"),   # shadow DOM
        (["iframe#mapa", "button.zamknij"], "iframe#mapa >>> button.zamknij"),  # iframe
        ([], ""),
        (None, ""),
    ],
)
def test_selektor_z_target(target, oczekiwany):
    assert selektor_z_target(target) == oczekiwany


def test_one_problem_per_element(wynik_axe):
    elementy = sum(len(r["nodes"]) for t in ("violations", "incomplete") for r in wynik_axe[t])
    assert len(axe_na_problemy(wynik_axe, URL)) == elementy == 6


def test_violation_becomes_error(problemy):
    p = problemy[("image-alt", "blad")]
    assert p.zrodlo == "axe"
    assert p.kryteria_wcag == ["1.1.1"]
    assert p.poziom_wcag == "A"
    assert p.waga == "krytyczna"
    assert p.poziom_pewnosci == 1.0
    assert p.selektor == 'img[src="a.png"]'
    assert p.fragment_html == '<img src="a.png">'
    assert p.url_podstrony == URL
    assert p.link_pomocy.startswith("https://dequeuniversity.com/rules/axe/")
    assert p.uzasadnienie is None


def test_messages_are_polish(problemy):
    p = problemy[("image-alt", "blad")]
    assert p.opis == "Obrazy muszą mieć tekst alternatywny."
    assert p.szczegoly.startswith("Napraw następujące elementy")


def test_rule_with_two_criteria(problemy):
    assert problemy[("link-name", "blad")].kryteria_wcag == ["2.4.4", "4.1.2"]


def test_incomplete_needs_verification(problemy):
    p = problemy[("color-contrast", "do_weryfikacji")]
    assert p.poziom_pewnosci is None
    assert p.poziom_wcag == "AA"
    assert p.waga == "powazna"


def test_impact_mapping():
    wynik = {"violations": [
        {"id": f"r-{impact}", "impact": impact, "tags": ["wcag2a"], "nodes": [{"target": ["x"], "html": ""}]}
        for impact in ("critical", "serious", "moderate", "minor")
    ] + [{"id": "r-none", "impact": None, "tags": [], "nodes": [{"target": ["x"]}]}]}
    wagi = {p.regula: p.waga for p in axe_na_problemy(wynik, URL)}
    assert wagi == {"r-critical": "krytyczna", "r-serious": "powazna", "r-moderate": "umiarkowana",
                    "r-minor": "drobna", "r-none": None}


def test_node_impact_overrides_rule_impact():
    wynik = {"violations": [{"id": "r", "impact": "critical", "tags": [],
                             "nodes": [{"target": ["a"], "impact": "minor"}]}]}
    assert axe_na_problemy(wynik, URL)[0].waga == "drobna"


def test_duplicate_elements_are_merged():
    node = {"target": ["img"], "html": "<img>"}
    wynik = {"violations": [{"id": "image-alt", "impact": "critical", "tags": [], "nodes": [node, node]}]}
    assert len(axe_na_problemy(wynik, URL)) == 1


def test_url_and_time_default_to_axe_result(wynik_axe):
    p = axe_na_problemy(wynik_axe)[0]
    assert p.url_podstrony == wynik_axe["url"]
    assert wynik_axe["timestamp"] == "2026-11-07T12:04:04.987Z"
    assert p.wykryto == "2026-11-07T12:04:04+00:00"          # format z kontraktu: UTC, bez ułamków


def test_ids_are_stable_between_runs(wynik_axe):
    pierwszy = [p.id for p in axe_na_problemy(wynik_axe, URL, "2026-11-07T10:00:00+00:00")]
    drugi = [p.id for p in axe_na_problemy(wynik_axe, URL, "2026-11-08T10:00:00+00:00")]
    assert pierwszy == drugi


def test_empty_result():
    assert axe_na_problemy({"violations": [], "incomplete": []}, URL) == []
