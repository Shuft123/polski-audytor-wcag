"""Krok: wykrycie i walidacja deklaracji dostępności (osoba 5, F17/F18) – do uzupełnienia w sprincie 2.

Krok skanu (raz na skan, po wszystkich podstronach) – deklaracja dotyczy całej witryny. Na razie nic nie robi.

Do zrobienia (podział pracy, sprint 2): wynik wykrywania deklaracji w przebiegu skanu i w bazie,
walidator v1 (sekcje B i C checklisty). Worker zapisuje `ctx.deklaracja` w tabeli `wynik_deklaracji`
(funkcja `zapisz_wynik_deklaracji`, migracja 0002); wynik walidatora – pod kluczem "walidacja".

Przydatne dane z kontekstu:
- `ctx.url_startowy` – adres witryny;
- `ctx.podstrony[0]` – wynik strony startowej; jej DOM z migawki:
  `ctx.folder_skanu / ctx.podstrony[0].migawka / "dom.html"` (bez ponownego pobierania strony);
- `ctx.otworz(url)` – strona w przeglądarce skanu (gdy deklaracja ładuje się przez JavaScript).

Przykład szkieletu:
    from audytor.deklaracja import find_declaration

    def sprawdz_deklaracje(ctx: KontekstSkanu) -> None:
        start = ctx.podstrony[0]
        html = (ctx.folder_skanu / start.migawka / "dom.html").read_text(encoding="utf-8")
        wynik = find_declaration(ctx.url_startowy, html=html, delay=ctx.ustawienia.opoznienie_s)
        ctx.deklaracja = wynik.to_dict()

Uwaga: `find_declaration` pobiera strony siecią – testy kroku w CI muszą podmienić `fetch` (bez internetu).
"""

from __future__ import annotations

from . import KontekstSkanu, KrokSkanu


def sprawdz_deklaracje(ctx: KontekstSkanu) -> None:
    """TODO(osoba 5): wyszukanie i walidacja deklaracji – wynik w ctx.deklaracja (DeclarationResult.to_dict())."""


KROK = KrokSkanu(nazwa="deklaracja", funkcja=sprawdz_deklaracje)
