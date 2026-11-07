"""Model danych v1 na SQLite w pamięci – bez PostgreSQL i bez przeglądarki."""

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, StatementError

from audytor.axe import axe_na_problemy
from audytor.db import Podstrona, Problem, Skan, StatusSkanu, otworz_baze, wynik_podstrony, zapisz_skan
from audytor.wyniki import WynikStrony

AXE = Path(__file__).parent.parent / "axe" / "data" / "axe_wynik_przyklad.json"
URL = "https://gmina-testowa.pl/"


@pytest.fixture
def sesje():
    return otworz_baze("sqlite://")


@pytest.fixture
def wynik():
    problemy = axe_na_problemy(json.loads(AXE.read_text(encoding="utf-8")), URL)
    return WynikStrony(
        url=URL,
        requested_url="https://gmina-testowa.pl",
        sprawdzono="2026-11-07T12:04:04+00:00",
        problemy=problemy,
        narzedzia={"audytor": "0.1.0", "axe-core": "4.12.1"},
        migawka="gmina-testowa-pl",
        http_status=200,
        ostrzezenia=["Sieć nie ucichła (networkidle)"],
    )


def test_save_scan_with_pages_and_problems(sesje, wynik):
    with sesje() as sesja:
        skan = zapisz_skan(sesja, [wynik], url_startowy=URL, parametry={"glebokosc": 1})
        sesja.commit()
        skan_id = skan.id

    with sesje() as sesja:
        skan = sesja.get(Skan, skan_id)
        assert skan.status == StatusSkanu.ZAKONCZONY
        assert skan.parametry == {"glebokosc": 1}
        assert len(skan.podstrony) == 1
        podstrona = skan.podstrony[0]
        assert podstrona.url == URL
        assert podstrona.ostrzezenia == ["Sieć nie ucichła (networkidle)"]
        assert len(podstrona.problemy) == 6
        bledy = sesja.scalar(select(func.count()).select_from(Problem).where(Problem.status == "blad"))
        assert bledy == 5


def test_roundtrip_back_to_result_format(sesje, wynik):
    with sesje() as sesja:
        skan = zapisz_skan(sesja, [wynik], url_startowy=URL)
        sesja.commit()
        odczytany = wynik_podstrony(skan.podstrony[0])
    assert odczytany.to_dict() == wynik.to_dict()


def test_enum_values_are_stored_as_contract_strings(sesje, wynik):
    with sesje() as sesja:
        zapisz_skan(sesja, [wynik], url_startowy=URL)
        sesja.commit()
        surowe = sesja.connection().exec_driver_sql(
            "SELECT DISTINCT status FROM problem ORDER BY status").scalars().all()
    assert surowe == ["blad", "do_weryfikacji"]


def test_invalid_status_is_rejected(sesje, wynik):
    with sesje() as sesja:
        skan = zapisz_skan(sesja, [wynik], url_startowy=URL)
        skan.podstrony[0].problemy[0].status = "zly-status"
        with pytest.raises((StatementError, LookupError)):
            sesja.flush()


def test_same_page_twice_in_scan_is_rejected(sesje, wynik):
    with sesje() as sesja:
        with pytest.raises(IntegrityError):
            zapisz_skan(sesja, [wynik, wynik], url_startowy=URL)


def test_deleting_scan_deletes_pages_and_problems(sesje, wynik):
    with sesje() as sesja:
        skan = zapisz_skan(sesja, [wynik], url_startowy=URL)
        sesja.commit()
        sesja.delete(skan)
        sesja.commit()
        assert sesja.scalar(select(func.count()).select_from(Podstrona)) == 0
        assert sesja.scalar(select(func.count()).select_from(Problem)) == 0


def test_same_problem_has_same_key_in_next_scan(sesje, wynik):
    with sesje() as sesja:
        zapisz_skan(sesja, [wynik], url_startowy=URL)
        zapisz_skan(sesja, [wynik], url_startowy=URL)
        sesja.commit()
        klucze = sesja.scalars(select(Problem.klucz).join(Podstrona).where(Podstrona.skan_id == 1)).all()
        klucze2 = sesja.scalars(select(Problem.klucz).join(Podstrona).where(Podstrona.skan_id == 2)).all()
    assert sorted(klucze) == sorted(klucze2)
