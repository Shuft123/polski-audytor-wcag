"""Zadanie workera: przejścia statusu skanu i zapis wyników (bez Celery-brokera i bez przeglądarki)."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from audytor.crawler.render import RenderError, RobotsDisallowedError
from audytor.db import Skan, StatusSkanu
from audytor.worker import ZADANIE_SKANU, app
from audytor.worker.zadania import wykonaj_skan

URL = "https://gmina-testowa.pl/"


def _nowy_skan(sesje, status=StatusSkanu.OCZEKUJE) -> int:
    with sesje() as sesja:
        skan = Skan(url_startowy=URL, status=status, utworzono=datetime.now(timezone.utc), parametry={})
        sesja.add(skan)
        sesja.commit()
        return skan.id


def test_successful_scan_saves_page_and_finishes(sesje, ustawienia, udawany_skan):
    skan_id = _nowy_skan(sesje)
    status = wykonaj_skan(sesje, skan_id, ustawienia, renderer=udawany_skan["renderer"])

    assert status == StatusSkanu.ZAKONCZONY
    with sesje() as sesja:
        skan = sesja.get(Skan, skan_id)
        assert skan.status == StatusSkanu.ZAKONCZONY
        assert skan.rozpoczeto is not None and skan.zakonczono is not None
        assert skan.opis_bledu is None
        assert len(skan.podstrony) == 1
        assert len(skan.podstrony[0].problemy) == 6
    # wyniki każdego skanu w osobnym folderze
    assert udawany_skan["wywolania"] == [(URL, ustawienia.wyniki_dir / f"skan-{skan_id}")]


@pytest.mark.parametrize(
    ("wyjatek", "poczatek_opisu"),
    [
        (RenderError("Przekroczono limit czasu"), "Przekroczono limit czasu"),
        (RobotsDisallowedError(URL, SimpleNamespace(status="ok", robots_url=URL + "robots.txt")),
         "Pominięto zgodnie z robots.txt"),
        (RuntimeError(), "RuntimeError"),
    ],
)
def test_failed_scan_is_marked_as_error(sesje, ustawienia, udawany_skan, wyjatek, poczatek_opisu):
    skan_id = _nowy_skan(sesje)
    udawany_skan["wyjatek"] = wyjatek

    assert wykonaj_skan(sesje, skan_id, ustawienia, renderer=udawany_skan["renderer"]) == StatusSkanu.BLAD
    with sesje() as sesja:
        skan = sesja.get(Skan, skan_id)
        assert skan.status == StatusSkanu.BLAD
        assert skan.opis_bledu.startswith(poczatek_opisu)
        assert skan.zakonczono is not None
        # sprint 2: niesprawdzona podstrona zostaje w bazie z powodem (pole blad), bez problemów
        assert [(p.url, p.problemy) for p in skan.podstrony] == [(URL, [])]
        assert skan.podstrony[0].blad.startswith(poczatek_opisu)


def test_scan_not_waiting_is_not_run_again(sesje, ustawienia, udawany_skan):
    skan_id = _nowy_skan(sesje, status=StatusSkanu.ZAKONCZONY)
    assert wykonaj_skan(sesje, skan_id, ustawienia, renderer=udawany_skan["renderer"]) == StatusSkanu.ZAKONCZONY
    assert udawany_skan["wywolania"] == []


def test_missing_scan_is_ignored(sesje, ustawienia, udawany_skan):
    assert wykonaj_skan(sesje, 999, ustawienia, renderer=udawany_skan["renderer"]) is None


def test_celery_task_is_registered_under_shared_name():
    from audytor.worker import zadania  # noqa: F401 – rejestruje zadanie (worker robi to przez include)

    assert ZADANIE_SKANU in app.tasks


def test_celery_task_runs_scan_eagerly(monkeypatch, sesje, ustawienia, udawany_skan):
    from audytor.worker import zadania

    monkeypatch.setenv("AUDYTOR_DB_URL", ustawienia.db_url)
    monkeypatch.setenv("AUDYTOR_WYNIKI_DIR", str(ustawienia.wyniki_dir))
    monkeypatch.setattr(zadania, "domyslny_renderer", udawany_skan["renderer"])
    domyslne = zadania.wykonaj_skan.__defaults__
    monkeypatch.setattr(zadania.wykonaj_skan, "__defaults__", (udawany_skan["renderer"], *domyslne[1:]))
    skan_id = _nowy_skan(sesje)

    wynik = zadania.skanuj_strone_zadanie.apply(args=[skan_id])

    assert wynik.get() == "zakonczony"
