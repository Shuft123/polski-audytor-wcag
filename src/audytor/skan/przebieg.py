"""„Chodzący szkielet” skanu jednej strony: adres -> render -> axe-core -> zapis wyniku.

    with Renderer() as renderer:
        wynik, folder = skanuj_strone(renderer, "https://www.gov.pl/", "wyniki")

W folderze wyniku lądują pliki migawki (dom.html, zrzut, meta.json – format z kontraktu, sekcja 1)
oraz wynik.json (format z kontraktu, sekcja 2).
"""

from __future__ import annotations

from pathlib import Path

from audytor import __version__
from audytor.axe import axe_na_problemy
from audytor.axe.uruchom import AxeError, uruchom_axe, wersja_axe
from audytor.crawler.render import Renderer
from audytor.crawler.snapshot import save_snapshot
from audytor.wyniki import WynikStrony, teraz_utc, zapisz_wynik


class SkanError(Exception):
    """Strona się wyrenderowała, ale audytu nie udało się przeprowadzić."""


def skanuj_strone(
    renderer: Renderer,
    url: str,
    out_dir: str | Path,
    name: str | None = None,
) -> tuple[WynikStrony, Path]:
    """Renderuje stronę, uruchamia axe-core na tej samej otwartej stronie i zapisuje migawkę + wynik.json.

    Wyjątki crawlera (RobotsDisallowedError, RenderError) przechodzą dalej bez zmian.
    Gdy axe-core zawiedzie, migawka i tak jest zapisywana, a funkcja zgłasza SkanError.
    """
    blad_axe: AxeError | None = None
    with renderer.open(url) as opened:
        sprawdzono = teraz_utc()
        try:
            wynik_axe = uruchom_axe(opened.page)
        except AxeError as exc:
            blad_axe, wynik_axe = exc, None
        # Migawka PO axe: axe nie zmienia treści strony, a zrzut i DOM pochodzą z tej samej sesji.
        snapshot = renderer.capture(opened)

    folder = save_snapshot(snapshot, out_dir, name=name)
    ostrzezenia = list(snapshot.warnings)
    if blad_axe is not None:
        ostrzezenia.append(str(blad_axe))

    wynik = WynikStrony(
        url=snapshot.final_url,
        requested_url=snapshot.requested_url,
        sprawdzono=sprawdzono,
        problemy=axe_na_problemy(wynik_axe, snapshot.final_url, sprawdzono) if wynik_axe else [],
        narzedzia={"audytor": __version__, "axe-core": wersja_axe()},
        migawka=folder.name,
        http_status=snapshot.http_status,
        ostrzezenia=ostrzezenia,
    )
    zapisz_wynik(wynik, folder)
    if blad_axe is not None:
        raise SkanError(f"{blad_axe} (migawka zapisana w {folder})") from blad_axe
    return wynik, folder
