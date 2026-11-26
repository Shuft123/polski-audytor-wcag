"""Zapis i odczyt wyników testu fokusu (F8) i deklaracji (F17/F18) – tabele z migracji 0002."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from audytor.db import (
    Problem,
    Skan,
    StatusSkanu,
    WynikDeklaracji,
    WynikFokusu,
    otworz_baze,
    wynik_deklaracji_dict,
    wynik_fokusu_dict,
    wynik_podstrony,
    zapisz_podstrone,
    zapisz_wynik_deklaracji,
    zapisz_wynik_fokusu,
)
from audytor.wyniki import WynikStrony

URL = "https://gmina-testowa.pl/"

# Kształt jak WynikFokusu.to_dict() z audytor.fokus (osoba 4) – skrócony do jednego kroku.
FOKUS = {
    "url": URL,
    "sprawdzono": "2026-11-26T12:00:00+00:00",
    "zakonczenie": "fokus wrócił na początek strony",
    "podsumowanie": {"kroki": 1, "ok": 0, "slaby": 0, "brak": 1, "niewidoczny": 0, "zgubiony": 0},
    "ostrzezenia": [],
    "problemy": [{
        "url_podstrony": URL,
        "zrodlo": "heurystyka",
        "regula": "fokus-niewidoczny",
        "kryteria_wcag": ["2.4.7"],
        "status": "do_weryfikacji",
        "selektor": "#menu > a",
        "fragment_html": "<a href=\"/\">Start</a>",
        "waga": "powazna",
        "poziom_wcag": "AA",
        "opis": "Brak widocznego wskaźnika fokusu",
        "szczegoly": "Wygląd elementu się nie zmienia.",
        "link_pomocy": "https://www.w3.org/WAI/WCAG21/Understanding/focus-visible",
        "poziom_pewnosci": 0.9,
        "uzasadnienie": None,
        "wykryto": "2026-11-26T12:00:00+00:00",
    }],
    "kroki": [{"nr": 1, "selektor": "#menu > a", "werdykt": "brak"}],
}

# Kształt jak DeclarationResult.to_dict() z audytor.deklaracja (osoba 5).
DEKLARACJA = {
    "site_url": URL,
    "found": True,
    "declaration_url": URL + "deklaracja-dostepnosci",
    "method": "link",
    "confidence": 0.95,
    "verified": True,
    "a11y_ids": ["a11y-wstep", "a11y-data-sporzadzenie"],
    "missing_required_ids": ["a11y-kontakt"],
    "candidates": [{"url": URL + "deklaracja-dostepnosci", "score": 90}],
    "warnings": [],
    "status": "zweryfikowana",
}


@pytest.fixture
def sesje():
    return otworz_baze("sqlite://")


@pytest.fixture
def skan_z_podstrona(sesje):
    sesja = sesje()
    skan = Skan(url_startowy=URL, status=StatusSkanu.W_TRAKCIE, utworzono=datetime.now(timezone.utc), parametry={})
    sesja.add(skan)
    podstrona = zapisz_podstrone(sesja, skan, WynikStrony(url=URL, requested_url=URL,
                                                          sprawdzono="2026-11-26T12:00:00+00:00"))
    yield sesja, skan, podstrona
    sesja.close()


def test_focus_result_saved_with_problems(skan_z_podstrona):
    sesja, _, podstrona = skan_z_podstrona
    zapisz_wynik_fokusu(sesja, podstrona, FOKUS, limit_krokow=60, mapa="mapa-fokusu.jpg")
    sesja.commit()

    assert sesja.scalar(select(func.count()).select_from(WynikFokusu)) == 1
    assert [(p.zrodlo, p.regula) for p in podstrona.problemy] == [("heurystyka", "fokus-niewidoczny")]
    odczyt = wynik_fokusu_dict(podstrona)
    assert odczyt["podsumowanie"]["brak"] == 1
    assert odczyt["limit_krokow"] == 60 and odczyt["mapa"] == "mapa-fokusu.jpg"
    assert odczyt["sprawdzono"] == "2026-11-26T12:00:00+00:00"
    # problemy fokusu są też w zwykłym wyniku podstrony (API /wyniki, raport)
    assert wynik_podstrony(podstrona).podsumowanie()["wg_zrodla"]["heurystyka"] == 1


def test_focus_saved_twice_replaces_result_and_skips_duplicate_problems(skan_z_podstrona):
    sesja, _, podstrona = skan_z_podstrona
    zapisz_wynik_fokusu(sesja, podstrona, FOKUS)
    zapisz_wynik_fokusu(sesja, podstrona, FOKUS)
    sesja.commit()
    assert sesja.scalar(select(func.count()).select_from(WynikFokusu)) == 1
    assert sesja.scalar(select(func.count()).select_from(Problem)) == 1


def test_focus_problem_with_wrong_source_is_rejected(skan_z_podstrona):
    sesja, _, podstrona = skan_z_podstrona
    zly = {**FOKUS, "problemy": [{**FOKUS["problemy"][0], "zrodlo": "piksele"}]}
    with pytest.raises(ValueError):
        zapisz_wynik_fokusu(sesja, podstrona, zly)


def test_page_without_focus_test(skan_z_podstrona):
    _, _, podstrona = skan_z_podstrona
    assert wynik_fokusu_dict(podstrona) is None


def test_declaration_saved_per_scan(skan_z_podstrona):
    sesja, skan, _ = skan_z_podstrona
    zapisz_wynik_deklaracji(sesja, skan, {**DEKLARACJA, "walidacja": {"sekcja_B": {"ok": 3, "brak": 1}}},
                            sprawdzono="2026-11-26T12:01:00+00:00")
    sesja.commit()

    odczyt = wynik_deklaracji_dict(skan)
    assert odczyt["znaleziono"] is True and odczyt["status"] == "zweryfikowana"
    assert odczyt["brakujace_identyfikatory"] == ["a11y-kontakt"]
    assert odczyt["walidacja"] == {"sekcja_B": {"ok": 3, "brak": 1}}
    assert odczyt["sprawdzono"] == "2026-11-26T12:01:00+00:00"

    zapisz_wynik_deklaracji(sesja, skan, {**DEKLARACJA, "found": False, "status": "brak"})
    sesja.commit()
    assert sesja.scalar(select(func.count()).select_from(WynikDeklaracji)) == 1
    assert wynik_deklaracji_dict(skan)["walidacja"] is None


def test_deleting_scan_deletes_focus_and_declaration(skan_z_podstrona):
    sesja, skan, podstrona = skan_z_podstrona
    zapisz_wynik_fokusu(sesja, podstrona, FOKUS)
    zapisz_wynik_deklaracji(sesja, skan, DEKLARACJA)
    sesja.commit()
    sesja.delete(skan)
    sesja.commit()
    assert sesja.scalar(select(func.count()).select_from(WynikFokusu)) == 0
    assert sesja.scalar(select(func.count()).select_from(WynikDeklaracji)) == 0


def test_page_error_is_stored(sesje):
    with sesje() as sesja:
        skan = Skan(url_startowy=URL, status=StatusSkanu.W_TRAKCIE, utworzono=datetime.now(timezone.utc),
                    parametry={})
        sesja.add(skan)
        p = zapisz_podstrone(sesja, skan, WynikStrony(url=URL + "a", requested_url=URL + "a",
                                                      sprawdzono="2026-11-26T12:00:00+00:00",
                                                      blad="Pominięto zgodnie z robots.txt"))
        sesja.commit()
        assert wynik_podstrony(p).blad == "Pominięto zgodnie z robots.txt"
