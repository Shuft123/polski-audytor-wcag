"""Skan wielu podstron (F6, sprint 2): lista adresów do sprawdzenia i limit tempa zapytań na witrynę.

Używają tego worker (`audytor.worker.zadania`) i komenda `audytor-scan`. Skąd lista podstron:
  - sprint 2: `url_startowy` skanu + podane jawnie `parametry["podstrony"]` (API, wiersz poleceń),
  - sprint 3: lista z crawlera wielu podstron (F1, osoba 1) – ta sama funkcja `lista_podstron`.

Parametry skanu (pole `parametry` w tabeli `skan`, docs/audyt-axe.md):
    "podstrony":    lista adresów do sprawdzenia oprócz strony startowej (tylko ta sama witryna),
    "max_podstron": ile podstron najwyżej (domyślnie 20, maks. 50) – licząc stronę startową.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from audytor.crawler.links import is_internal, normalize_url

DOMYSLNIE_MAX_PODSTRON = 20
LIMIT_PODSTRON = 50            # twardy limit – skan dłuższej listy to zadanie kolejki (F4, sprint 3)
DOMYSLNE_OPOZNIENIE_S = 1.0    # pauza między zapytaniami do tej samej witryny


@dataclass
class ListaPodstron:
    adresy: list[str]                                   # do sprawdzenia, strona startowa pierwsza
    pominiete: list[str] = field(default_factory=list)  # komunikaty: co i dlaczego pominięto


def _liczba(wartosc: object, domyslnie: int) -> int:
    try:
        return int(wartosc)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return domyslnie


def lista_podstron(url_startowy: str, parametry: dict | None = None) -> ListaPodstron:
    """Strona startowa + `parametry["podstrony"]`: znormalizowane, bez duplikatów, tylko ta sama witryna,
    najwyżej `parametry["max_podstron"]` adresów (domyślnie 20, nie więcej niż 50)."""
    parametry = parametry or {}
    start = normalize_url(url_startowy) or url_startowy
    limit = min(max(_liczba(parametry.get("max_podstron"), DOMYSLNIE_MAX_PODSTRON), 1), LIMIT_PODSTRON)
    podane = parametry.get("podstrony") or []
    if isinstance(podane, str):
        podane = [podane]

    wynik = ListaPodstron(adresy=[start])
    widziane = {start}
    nadmiarowe = 0
    for surowy in podane:
        url = normalize_url(str(surowy))   # bez fragmentu #, z ukośnikiem po domenie
        if url is None:
            wynik.pominiete.append(f"{surowy}: nieprawidłowy adres")
        elif url in widziane:
            continue                        # duplikat – bez komunikatu
        elif not is_internal(url, start):
            wynik.pominiete.append(f"{url}: inna witryna niż {start}")
        elif len(wynik.adresy) >= limit:
            nadmiarowe += 1
        else:
            wynik.adresy.append(url)
        if url is not None:
            widziane.add(url)
    if nadmiarowe:
        wynik.pominiete.append(f"pominięto {nadmiarowe} podstron ponad limit {limit}")
    return wynik


class Ogranicznik:
    """Limit tempa zapytań na witrynę: między stronami tego samego hosta czeka `opoznienie_s`
    albo Crawl-delay z robots.txt, jeśli jest większy.

    `crawl_delay(url)` – zwraca Crawl-delay dla adresu (np. z `Renderer.robots`) albo None.
    `zegar` i `spij` można podmienić w testach.
    """

    def __init__(
        self,
        opoznienie_s: float = DOMYSLNE_OPOZNIENIE_S,
        crawl_delay: Callable[[str], float | None] | None = None,
        zegar: Callable[[], float] = time.monotonic,
        spij: Callable[[float], None] = time.sleep,
    ):
        self.opoznienie_s = max(opoznienie_s, 0.0)
        self._crawl_delay = crawl_delay
        self._zegar = zegar
        self._spij = spij
        self._ostatnio: dict[str, float] = {}

    @staticmethod
    def _host(url: str) -> str:
        return (urlsplit(url).hostname or "").removeprefix("www.")

    def pauza(self, url: str) -> float:
        """Ile sekund trzeba jeszcze poczekać przed zapytaniem o `url` (0 = można od razu)."""
        host = self._host(url)
        if host not in self._ostatnio:
            return 0.0
        odstep = self.opoznienie_s
        if self._crawl_delay is not None:
            odstep = max(odstep, self._crawl_delay(url) or 0.0)
        return max(odstep - (self._zegar() - self._ostatnio[host]), 0.0)

    def czekaj(self, url: str) -> None:
        pauza = self.pauza(url)
        if pauza > 0:
            self._spij(pauza)

    def odwiedzono(self, url: str) -> None:
        self._ostatnio[self._host(url)] = self._zegar()


def crawl_delay_z_renderera(renderer: object) -> Callable[[str], float | None] | None:
    """Crawl-delay z robots.txt, który wczytał już Renderer (None, gdy renderer go nie ma, np. w testach)."""
    robots = getattr(renderer, "robots", None)
    if robots is None:
        return None
    return lambda url: robots.policy_for(url).crawl_delay()
