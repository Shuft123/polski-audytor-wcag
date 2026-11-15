"""Wspólne dane dla testów API i workera – SQLite w pliku tymczasowym, bez Redisa i bez przeglądarki."""

import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from audytor.axe import axe_na_problemy
from audytor.db import otworz_baze
from audytor.ustawienia import Ustawienia
from audytor.wyniki import WynikStrony

AXE = Path(__file__).parent.parent / "axe" / "data" / "axe_wynik_przyklad.json"
URL = "https://gmina-testowa.pl/"


@pytest.fixture
def ustawienia(tmp_path):
    return Ustawienia(db_url=f"sqlite:///{tmp_path / 'audytor.db'}", wyniki_dir=tmp_path / "wyniki")


@pytest.fixture
def sesje(ustawienia):
    return otworz_baze(ustawienia.db_url)


@pytest.fixture
def wynik_strony():
    problemy = axe_na_problemy(json.loads(AXE.read_text(encoding="utf-8")), URL)
    return WynikStrony(
        url=URL,
        requested_url=URL,
        sprawdzono="2026-11-07T12:04:04+00:00",
        problemy=problemy,
        narzedzia={"audytor": "0.1.0", "axe-core": "4.12.1"},
        migawka="gmina-testowa-pl",
        http_status=200,
    )


@pytest.fixture
def udawany_skan(monkeypatch, wynik_strony):
    """Podmienia render + axe-core w workerze: zwraca gotowy wynik albo zgłasza podany wyjątek."""
    from audytor.worker import zadania

    stan = {"wyjatek": None, "wywolania": []}

    def skanuj(renderer, url, out_dir, name=None):
        stan["wywolania"].append((url, Path(out_dir)))
        if stan["wyjatek"] is not None:
            raise stan["wyjatek"]
        return wynik_strony, Path(out_dir) / "gmina-testowa-pl"

    monkeypatch.setattr(zadania, "skanuj_strone", skanuj)
    stan["renderer"] = lambda _ustawienia: nullcontext(None)
    return stan
