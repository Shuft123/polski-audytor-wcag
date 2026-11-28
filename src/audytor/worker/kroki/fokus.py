"""Krok: test widoczności fokusu (osoba 4, F8, WCAG 2.4.7) – do uzupełnienia w sprincie 2.

Domyślnie tylko dla strony startowej (`tylko_startowa=True`): przejście Tabem jest wolne, a budżet
całego skanu to ok. 8 minut (`BUDZET_S` w zadania.py). Zmiana na wszystkie podstrony – decyzja osoby 4.
Na razie krok nic nie robi.

Do zrobienia (podział pracy, sprint 2): test fokusu w przebiegu skanu z limitem kroków, wynik w bazie.
Worker zapisuje `ctx.fokus` w tabeli `wynik_fokusu` (funkcja `zapisz_wynik_fokusu`, migracja 0002), razem
z problemami z `ctx.fokus["problemy"]` – nie trzeba ich dopisywać osobno przez ctx.dodaj_problemy().

Strona musi być otwarta na nowo (axe-core i migawka już ją zamknęły), np.:
    from audytor.fokus import mapa_fokusu, przejdz_tabem

    LIMIT_KROKOW = 40

    def test_fokusu(ctx: KontekstPodstrony) -> None:
        with ctx.otworz(ctx.url) as opened:
            wynik = przejdz_tabem(opened.page, url=opened.final_url, max_krokow=LIMIT_KROKOW)
            if ctx.folder is not None:
                mapa_fokusu(opened.page, wynik).save(ctx.folder / "mapa-fokusu.png")
                ctx.fokus_mapa = "mapa-fokusu.png"
        ctx.fokus = wynik.to_dict()
        ctx.fokus_limit_krokow = LIMIT_KROKOW

`ctx.pozostalo_s()` mówi, ile sekund zostało z budżetu skanu – można z niego wyliczyć limit kroków.
"""

from __future__ import annotations

from . import KontekstPodstrony, KrokPodstrony


def test_fokusu(ctx: KontekstPodstrony) -> None:
    """TODO(osoba 4): przejście Tabem po podstronie – wynik w ctx.fokus (WynikFokusu.to_dict())."""


KROK = KrokPodstrony(nazwa="fokus", funkcja=test_fokusu, tylko_startowa=True)
