"""Migracja 0002 (sprint 2): fokus, deklaracja, źródło „heurystyka”, błąd podstrony – na SQLite.

Na PostgreSQL te same kroki (upgrade, alembic check, downgrade) wykonuje CI (zadanie „migracje”).
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def baza(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migracje.db'}"
    monkeypatch.setenv("AUDYTOR_DB_URL", url)
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg, create_engine(url)


def _problem(c, zrodlo: str, klucz: str = "k1") -> None:
    c.execute(text(
        "INSERT INTO problem (podstrona_id, klucz, zrodlo, regula, kryteria_wcag, status, selektor, "
        "fragment_html, opis, szczegoly, wykryto) "
        "VALUES (1, :k, :z, 'fokus-niewidoczny', '[]', 'do_weryfikacji', 'a', '', '', '', '2026-11-26')"
    ), {"k": klucz, "z": zrodlo})


def _skan_z_podstrona(c) -> None:
    c.execute(text("INSERT INTO skan (url_startowy, status, utworzono, parametry) "
                   "VALUES ('https://p.pl/', 'zakonczony', '2026-11-26', '{}')"))
    c.execute(text("INSERT INTO podstrona (skan_id, url, requested_url, sprawdzono, narzedzia, ostrzezenia) "
                   "VALUES (1, 'https://p.pl/', 'https://p.pl/', '2026-11-26', '{}', '[]')"))


def test_upgrade_adds_tables_and_column(baza):
    cfg, engine = baza
    command.upgrade(cfg, "head")
    insp = inspect(engine)
    assert {"wynik_fokusu", "wynik_deklaracji"} <= set(insp.get_table_names())
    assert "blad" in {k["name"] for k in insp.get_columns("podstrona")}


def test_heuristic_source_allowed_and_unknown_rejected(baza):
    cfg, engine = baza
    command.upgrade(cfg, "head")
    with engine.begin() as c:
        _skan_z_podstrona(c)
        _problem(c, "heurystyka")
    with pytest.raises(IntegrityError), engine.begin() as c:
        _problem(c, "lighthouse", klucz="k2")


def test_one_focus_result_per_page(baza):
    cfg, engine = baza
    command.upgrade(cfg, "head")
    wstaw = text("INSERT INTO wynik_fokusu (podstrona_id, sprawdzono, zakonczenie, podsumowanie, kroki, ostrzezenia) "
                 "VALUES (1, '2026-11-26', '', '{}', '[]', '[]')")
    with engine.begin() as c:
        _skan_z_podstrona(c)
        c.execute(wstaw)
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(wstaw)


def test_downgrade_to_0001_keeps_data_and_maps_heuristic_to_ai(baza):
    cfg, engine = baza
    command.upgrade(cfg, "head")
    with engine.begin() as c:
        _skan_z_podstrona(c)
        _problem(c, "heurystyka")
    command.downgrade(cfg, "0001")
    insp = inspect(engine)
    assert "wynik_fokusu" not in insp.get_table_names()
    assert "blad" not in {k["name"] for k in insp.get_columns("podstrona")}
    with engine.connect() as c:
        assert c.execute(text("SELECT zrodlo FROM problem")).scalar() == "ai"
    command.upgrade(cfg, "head")       # i z powrotem
