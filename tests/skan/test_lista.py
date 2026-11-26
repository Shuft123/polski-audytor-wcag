"""Lista podstron skanu i limit tempa zapytań na witrynę (audytor.skan.lista) – bez sieci."""

from audytor.skan import Ogranicznik, lista_podstron
from audytor.skan.lista import LIMIT_PODSTRON

START = "https://www.gmina.pl/"


def test_start_page_first_then_given_pages_normalized_without_duplicates():
    lista = lista_podstron("https://www.gmina.pl", {"podstrony": [
        "https://www.gmina.pl/kontakt", "https://www.gmina.pl/kontakt#mapa", "https://www.gmina.pl/",
        "https://gmina.pl/aktualnosci",          # bez www. – ta sama witryna
    ]})
    assert lista.adresy == [START, START + "kontakt", "https://gmina.pl/aktualnosci"]
    assert lista.pominiete == []


def test_other_sites_subdomains_and_bad_urls_are_skipped_with_reason():
    lista = lista_podstron(START, {"podstrony": ["https://bip.gmina.pl/", "https://example.com/", "mailto:a@b.pl"]})
    assert lista.adresy == [START]
    assert len(lista.pominiete) == 3
    assert any("bip.gmina.pl" in p and "inna witryna" in p for p in lista.pominiete)
    assert any("nieprawidłowy adres" in p for p in lista.pominiete)


def test_limit_counts_start_page_and_is_capped():
    podstrony = [f"{START}s{i}" for i in range(100)]
    assert len(lista_podstron(START, {"podstrony": podstrony}).adresy) == 20           # domyślnie
    lista = lista_podstron(START, {"podstrony": podstrony, "max_podstron": 5})
    assert lista.adresy == [START] + podstrony[:4]
    assert lista.pominiete == ["pominięto 96 podstron ponad limit 5"]
    assert len(lista_podstron(START, {"podstrony": podstrony, "max_podstron": 999}).adresy) == LIMIT_PODSTRON
    assert len(lista_podstron(START, {"podstrony": podstrony, "max_podstron": "abc"}).adresy) == 20


def test_no_parameters_means_only_start_page():
    assert lista_podstron(START, None).adresy == [START]
    assert lista_podstron(START, {"podstrony": START + "jedna"}).adresy == [START, START + "jedna"]


class _Zegar:
    def __init__(self):
        self.t = 100.0
        self.pauzy = []

    def __call__(self):
        return self.t

    def spij(self, s):
        self.pauzy.append(s)
        self.t += s


def test_rate_limit_per_host():
    zegar = _Zegar()
    o = Ogranicznik(opoznienie_s=2.0, zegar=zegar, spij=zegar.spij)
    o.czekaj(START)                       # pierwsza strona – od razu
    o.odwiedzono(START)
    zegar.t += 0.5
    o.czekaj("https://example.com/")      # inna witryna – od razu
    o.czekaj("https://gmina.pl/a")        # ta sama witryna (bez www.) – reszta z 2 s
    assert zegar.pauzy == [1.5]


def test_crawl_delay_from_robots_wins_when_longer():
    zegar = _Zegar()
    o = Ogranicznik(opoznienie_s=1.0, crawl_delay=lambda url: 5.0, zegar=zegar, spij=zegar.spij)
    o.odwiedzono(START)
    assert o.pauza(START + "a") == 5.0
    o2 = Ogranicznik(opoznienie_s=3.0, crawl_delay=lambda url: None, zegar=zegar, spij=zegar.spij)
    o2.odwiedzono(START)
    assert o2.pauza(START + "a") == 3.0
