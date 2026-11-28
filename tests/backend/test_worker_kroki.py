"""Punkty podpięcia modułów pod skan (audytor.worker.kroki) – bez brokera Celery i bez przeglądarki."""

import json
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from audytor.axe import axe_na_problemy
from audytor.db import Skan, StatusSkanu, wynik_deklaracji_dict, wynik_fokusu_dict
from audytor.worker.kroki import (
    KontekstPodstrony,
    KrokPodstrony,
    Kroki,
    KrokSkanu,
    domyslne_kroki,
    uruchom_kroki_podstrony,
)
from audytor.wyniki import WynikStrony, wczytaj_wynik

AXE = Path(__file__).parent.parent / "axe" / "data" / "axe_wynik_przyklad.json"
START = "https://gmina-testowa.pl/"
KONTAKT = START + "kontakt"


def _problem_alt(url: str) -> dict:
    return {
        "url_podstrony": url, "zrodlo": "heurystyka", "regula": "alt-nazwa-pliku", "kryteria_wcag": ["1.1.1"],
        "status": "do_weryfikacji", "selektor": "img.herb", "poziom_wcag": "A", "poziom_pewnosci": 0.7,
        "opis": "Tekst alternatywny wygląda jak nazwa pliku",
    }


def _fokus(url: str) -> dict:
    return {
        "url": url, "sprawdzono": "2026-11-28T12:00:00+00:00", "zakonczenie": "powrót do początku",
        "podsumowanie": {"kroki": 1, "ok": 0, "brak": 1}, "kroki": [{"nr": 1, "selektor": "a.menu"}],
        "ostrzezenia": [],
        "problemy": [{
            "url_podstrony": url, "zrodlo": "heurystyka", "regula": "fokus-niewidoczny", "kryteria_wcag": ["2.4.7"],
            "status": "do_weryfikacji", "selektor": "a.menu", "poziom_wcag": "AA",
        }],
    }


DEKLARACJA = {
    "found": True, "declaration_url": START + "deklaracja-dostepnosci", "method": "link", "status": "ok",
    "confidence": 0.95, "verified": True, "a11y_ids": ["a11y-wstep"], "missing_required_ids": [],
    "candidates": [], "warnings": [],
}


class _Przegladarka:
    """Udaje Renderer: open() oddaje „stronę” z final_url i zapamiętuje otwarte adresy."""

    def __init__(self):
        self.otwarte: list[str] = []

    @contextmanager
    def open(self, url):
        self.otwarte.append(url)
        yield SimpleNamespace(page="strona", final_url=url)


@pytest.fixture
def skan(sesje, ustawienia, monkeypatch):
    """Skan dwóch podstron z podmienionym skanuj_strone; zwraca funkcję uruchom(kroki, parametry)."""
    from audytor.worker import zadania

    def skanuj(renderer, url, out_dir, name=None):
        wynik = WynikStrony(url=url, requested_url=url, sprawdzono="2026-11-28T12:00:00+00:00",
                            problemy=axe_na_problemy(json.loads(AXE.read_text(encoding="utf-8")), url),
                            migawka=url.rstrip("/").rsplit("/", 1)[-1])
        return wynik, Path(out_dir) / wynik.migawka

    monkeypatch.setattr(zadania, "skanuj_strone", skanuj)
    przegladarka = _Przegladarka()

    def uruchom(kroki: Kroki, parametry: dict | None = None):
        parametry = {"podstrony": [KONTAKT], **(parametry or {})}
        with sesje() as sesja:
            s = Skan(url_startowy=START, status=StatusSkanu.OCZEKUJE, utworzono=datetime.now(timezone.utc),
                     parametry=parametry)
            sesja.add(s)
            sesja.commit()
            skan_id = s.id
        status = zadania.wykonaj_skan(sesje, skan_id, ustawienia, renderer=lambda _u: nullcontext(przegladarka),
                                      spij=lambda _s: None, kroki=kroki)
        return status, skan_id

    uruchom.przegladarka = przegladarka
    return uruchom


def test_default_steps_have_one_file_per_module():
    kroki = domyslne_kroki()
    assert [k.nazwa for k in kroki.podstrony] == ["alt", "fokus"]
    assert [k.nazwa for k in kroki.skanu] == ["deklaracja"]
    assert next(k for k in kroki.podstrony if k.nazwa == "fokus").tylko_startowa


def test_default_steps_are_noop_until_modules_are_plugged_in(sesje, skan):
    status, skan_id = skan(domyslne_kroki())
    assert status == StatusSkanu.ZAKONCZONY
    with sesje() as sesja:
        s = sesja.get(Skan, skan_id)
        assert all(len(p.problemy) == 6 and p.fokus is None for p in s.podstrony)
        assert s.deklaracja is None


def test_page_step_problems_go_to_database_and_wynik_json(sesje, skan, ustawienia):
    def alt(ctx: KontekstPodstrony):
        assert ctx.folder is not None and ctx.parametry["podstrony"] == [KONTAKT]
        assert ctx.dodaj_problemy([_problem_alt(ctx.url)]) == 1
        assert ctx.dodaj_problemy([_problem_alt(ctx.url)]) == 0       # ten sam problem drugi raz – pomijany

    status, skan_id = skan(Kroki(podstrony=(KrokPodstrony("alt", alt),)))

    assert status == StatusSkanu.ZAKONCZONY
    with sesje() as sesja:
        s = sesja.get(Skan, skan_id)
        for p in s.podstrony:
            assert len(p.problemy) == 7
            assert {pr.zrodlo for pr in p.problemy} == {"axe", "heurystyka"}
    plik = ustawienia.wyniki_dir / f"skan-{skan_id}" / "kontakt" / "wynik.json"
    assert any(p.regula == "alt-nazwa-pliku" for p in wczytaj_wynik(plik).problemy)


def test_focus_result_saved_only_for_start_page(sesje, skan):
    odwiedzone = []

    def fokus(ctx: KontekstPodstrony):
        with ctx.otworz(ctx.url) as opened:
            odwiedzone.append(opened.final_url)
        ctx.fokus = _fokus(ctx.url)
        ctx.fokus_limit_krokow = 40

    status, skan_id = skan(Kroki(podstrony=(KrokPodstrony("fokus", fokus, tylko_startowa=True),)))

    assert status == StatusSkanu.ZAKONCZONY
    assert odwiedzone == [START] and skan.przegladarka.otwarte == [START]
    with sesje() as sesja:
        start, kontakt = sesja.get(Skan, skan_id).podstrony
        wynik = wynik_fokusu_dict(start)
        assert wynik["limit_krokow"] == 40 and wynik["kroki"] == [{"nr": 1, "selektor": "a.menu"}]
        assert any(p.regula == "fokus-niewidoczny" for p in start.problemy)
        assert wynik_fokusu_dict(kontakt) is None


def test_scan_step_declaration_saved(sesje, skan, ustawienia):
    def deklaracja(ctx):
        assert [p.url for p in ctx.podstrony] == [START, KONTAKT]
        assert ctx.folder_skanu == ustawienia.wyniki_dir / f"skan-{ctx.skan_id}"
        ctx.deklaracja = DEKLARACJA

    status, skan_id = skan(Kroki(skanu=(KrokSkanu("deklaracja", deklaracja),)))

    assert status == StatusSkanu.ZAKONCZONY
    with sesje() as sesja:
        wynik = wynik_deklaracji_dict(sesja.get(Skan, skan_id))
        assert wynik["znaleziono"] and wynik["url_deklaracji"] == START + "deklaracja-dostepnosci"


def test_failing_steps_do_not_break_scan(sesje, skan):
    def zepsuty(ctx):
        raise RuntimeError("model nie odpowiada")

    def zepsuta_deklaracja(ctx):
        raise ConnectionError("brak sieci")

    status, skan_id = skan(Kroki(podstrony=(KrokPodstrony("alt", zepsuty),),
                                 skanu=(KrokSkanu("deklaracja", zepsuta_deklaracja),)))

    assert status == StatusSkanu.ZAKONCZONY
    with sesje() as sesja:
        s = sesja.get(Skan, skan_id)
        for p in s.podstrony:
            assert len(p.problemy) == 6                                   # axe-core zapisany mimo błędu kroku
            assert any("Krok „alt” nie powiódł się: model nie odpowiada" in o for o in p.ostrzezenia)
        assert s.deklaracja is None


def test_steps_can_be_skipped_per_scan(sesje, skan):
    wywolane = []
    kroki = Kroki(podstrony=(KrokPodstrony("alt", lambda ctx: wywolane.append("alt")),),
                  skanu=(KrokSkanu("deklaracja", lambda ctx: wywolane.append("deklaracja")),))

    status, _ = skan(kroki, {"pomin_kroki": ["alt", "deklaracja"]})

    assert status == StatusSkanu.ZAKONCZONY and wywolane == []


def test_page_steps_skipped_when_scan_time_is_up():
    wynik = WynikStrony(url=START, requested_url=START, sprawdzono="2026-11-28T12:00:00+00:00")
    ctx = KontekstPodstrony(skan_id=1, wynik=wynik, folder=None, jest_startowa=True, ustawienia=None,
                            parametry={}, otworz=None, pozostalo_s=lambda: 0)
    wywolane = []

    uruchom_kroki_podstrony([KrokPodstrony("fokus", lambda c: wywolane.append(1))], ctx)

    assert wywolane == []
    assert wynik.ostrzezenia == ["Krok „fokus” pominięty – przekroczony czas skanu"]
