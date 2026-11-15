"""REST API na SQLite – kolejka podmieniona, więc bez Redisa, Celery-workera i przeglądarki."""

import pytest
from fastapi.testclient import TestClient

from audytor.api import create_app
from audytor.db import otworz_baze
from audytor.worker.zadania import wykonaj_skan

URL = "https://gmina-testowa.pl/"


@pytest.fixture
def kolejka():
    class Kolejka:
        def __init__(self):
            self.wyslane: list[int] = []
            self.dziala = True

        def __call__(self, skan_id: int) -> None:
            if not self.dziala:
                raise ConnectionError("Redis nie odpowiada")
            self.wyslane.append(skan_id)

    return Kolejka()


@pytest.fixture
def klient(ustawienia, sesje, kolejka):
    app = create_app(ustawienia, sesje=sesje, kolejka=kolejka, sprawdz_kolejke=lambda: kolejka.dziala)
    with TestClient(app) as klient:
        yield klient


def test_health_ok(klient):
    odp = klient.get("/health")
    assert odp.status_code == 200
    assert odp.json() == {"status": "ok", "wersja": "0.1.0", "baza": "ok", "kolejka": "ok"}


def test_health_reports_missing_tables(ustawienia, kolejka):
    pusta = otworz_baze(ustawienia.db_url, utworz=False)
    app = create_app(ustawienia, sesje=pusta, kolejka=kolejka, sprawdz_kolejke=lambda: True)
    odp = TestClient(app).get("/health")
    assert odp.status_code == 503
    assert odp.json()["baza"].startswith("brak tabel")


def test_health_reports_queue_down(klient, kolejka):
    kolejka.dziala = False
    odp = klient.get("/health")
    assert odp.status_code == 503
    assert odp.json()["kolejka"] == "niedostepna"


def test_create_scan_queues_it(klient, kolejka):
    odp = klient.post("/skany", json={"url": "HTTPS://Gmina-Testowa.pl", "parametry": {"glebokosc": 1}})

    assert odp.status_code == 202
    skan = odp.json()
    assert skan["status"] == "oczekuje"
    assert skan["url_startowy"] == URL            # znormalizowany adres
    assert skan["parametry"] == {"glebokosc": 1}
    assert skan["liczba_podstron"] == 0
    assert odp.headers["Location"] == f"/skany/{skan['id']}"
    assert kolejka.wyslane == [skan["id"]]


@pytest.mark.parametrize("url", ["gmina-testowa.pl", "ftp://gmina-testowa.pl/", "mailto:urzad@gmina.pl", ""])
def test_create_scan_rejects_invalid_url(klient, kolejka, url):
    odp = klient.post("/skany", json={"url": url})
    assert odp.status_code == 422
    assert kolejka.wyslane == []


def test_create_scan_when_queue_is_down(klient, kolejka):
    kolejka.dziala = False
    odp = klient.post("/skany", json={"url": URL})
    assert odp.status_code == 503

    skan = klient.get("/skany").json()[0]
    assert skan["status"] == "blad"
    assert "kolejki" in skan["opis_bledu"]


def test_get_missing_scan_returns_404(klient):
    assert klient.get("/skany/12345").status_code == 404
    assert klient.get("/skany/12345/wyniki").status_code == 404


def test_list_scans_newest_first(klient):
    ids = [klient.post("/skany", json={"url": URL}).json()["id"] for _ in range(3)]
    lista = klient.get("/skany", params={"limit": 2}).json()
    assert [s["id"] for s in lista] == ids[::-1][:2]


def test_full_flow_api_worker_results(klient, kolejka, sesje, ustawienia, udawany_skan):
    """Chodzący szkielet przez API: POST -> worker wykonuje skan -> GET status i wyniki."""
    skan_id = klient.post("/skany", json={"url": URL}).json()["id"]
    assert klient.get(f"/skany/{skan_id}/wyniki").json()["podstrony"] == []

    wykonaj_skan(sesje, kolejka.wyslane[0], ustawienia, renderer=udawany_skan["renderer"])

    skan = klient.get(f"/skany/{skan_id}").json()
    assert skan["status"] == "zakonczony"
    assert skan["liczba_podstron"] == 1 and skan["liczba_problemow"] == 6
    assert skan["zakonczono"].endswith("+00:00") or skan["zakonczono"].endswith("Z")

    wyniki = klient.get(f"/skany/{skan_id}/wyniki").json()
    [strona] = wyniki["podstrony"]
    assert strona["url"] == URL
    assert strona["podsumowanie"]["wg_statusu"]["blad"] == 5
    assert {p["regula"] for p in strona["problemy"]} >= {"image-alt", "color-contrast"}


def test_openapi_docs_available(klient):
    sciezki = klient.get("/openapi.json").json()["paths"]
    assert {"/health", "/skany", "/skany/{skan_id}", "/skany/{skan_id}/wyniki"} <= set(sciezki)
