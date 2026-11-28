"""Krok: ocena tekstu alternatywnego obrazów (osoba 3, F9/F10) – do uzupełnienia w sprincie 2.

Uruchamiany dla każdej sprawdzonej podstrony, po axe-core. Na razie nic nie robi.

Do zrobienia (podział pracy, sprint 2):
- moduł oceny altu w `src/audytor/ai/` (przeniesiony z notatnika F9_ocena_alt_colab.ipynb), z testami;
- tutaj tylko wywołanie go i dopisanie wyników: `ctx.dodaj_problemy([...])`, problemy ze źródłem
  "ai" (albo "heurystyka" w trybie bez modelu), statusem "do_weryfikacji" i `poziom_pewnosci`;
- tryb bez modelu (same reguły) – w nim działają testy w CI i domyślny docker-compose.

Skąd brać dane o obrazach (do wyboru):
- `ctx.folder / "dom.html"` – DOM z migawki (alt, src, otoczenie obrazu), bez ponownego ładowania strony;
- `ctx.wynik.problemy` – problemy axe (np. `image-alt`), żeby nie zgłaszać drugi raz tego samego;
- `with ctx.otworz(ctx.url) as opened:` – strona na żywo (np. zrzut pojedynczego obrazu dla modelu
  wizyjnego, format opisu uzgadniany z osobą 4). Kosztuje ponowne wczytanie strony.

Przykład szkieletu:
    from audytor.ai import ocen_alty_w_html          # moduł osoby 3

    def ocen_alty(ctx: KontekstPodstrony) -> None:
        html = (ctx.folder / "dom.html").read_text(encoding="utf-8")
        ctx.dodaj_problemy(ocen_alty_w_html(html, ctx.url))
"""

from __future__ import annotations

from . import KontekstPodstrony, KrokPodstrony


def ocen_alty(ctx: KontekstPodstrony) -> None:
    """TODO(osoba 3): ocena altów obrazów podstrony – wyniki przez ctx.dodaj_problemy()."""


KROK = KrokPodstrony(nazwa="alt", funkcja=ocen_alty)
