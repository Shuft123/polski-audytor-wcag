"""Wymagania wobec deklaracji dostępności – wersja maszynowa checklisty.

Źródło: „Warunki techniczne publikacji oraz struktura dokumentu elektronicznego
deklaracji dostępności”, wersja 2.0 z 31 lipca 2024 r. (Ministerstwo Cyfryzacji,
na podstawie art. 12 pkt 7 ustawy z dnia 4 kwietnia 2019 r. o dostępności cyfrowej).
Opis dla ludzi: docs/deklaracja-checklista.md – oba pliki trzeba zmieniać razem.

Ten plik jest punktem wyjścia dla walidatora deklaracji (F18, sprint 3–4).
W sprincie 1/2 korzysta z niego tylko weryfikacja kandydatów w `wyszukiwanie.py`
(strona z deklaracją ma identyfikatory a11y-*).
"""

from __future__ import annotations

from dataclasses import dataclass

WERSJA_WARUNKOW = "2.0 (31.07.2024)"

# Statusy wymagalności identyfikatora
OBOWIAZKOWY = "obowiazkowy"
OPCJONALNY = "opcjonalny"
WARUNKOWY = "warunkowy"  # obowiązkowy tylko w określonej sytuacji (opis w polu `warunek`)


@dataclass(frozen=True)
class Identyfikator:
    id: str
    tresc: str
    status: str
    warunek: str = ""


IDENTYFIKATORY: tuple[Identyfikator, ...] = (
    Identyfikator("a11y-wstep", "cała treść oświadczenia wstępnego", OBOWIAZKOWY),
    Identyfikator("a11y-podmiot", "nazwa podmiotu publicznego", OBOWIAZKOWY),
    Identyfikator("a11y-zakres", "rodzaj rozwiązania: „strona internetowa” albo „aplikacja mobilna”", OBOWIAZKOWY),
    Identyfikator("a11y-url", "adres strony / adres, z którego pobiera się aplikację", OBOWIAZKOWY),
    Identyfikator("a11y-data-publikacja", "data publikacji strony / wydania aplikacji", OBOWIAZKOWY),
    Identyfikator("a11y-data-aktualizacja", "data ostatniej istotnej aktualizacji (wpływającej na dostępność)", OBOWIAZKOWY),
    Identyfikator("a11y-status", "cały akapit ze stanem zgodności z załącznikiem do ustawy", OBOWIAZKOWY),
    Identyfikator("a11y-ocena", "ocena nadmiernych kosztów albo link do jej wyników", WARUNKOWY,
                  "gdy deklaracja powołuje się na nadmierne koszty (art. 8 ust. 3–4)"),
    Identyfikator("a11y-data-sporzadzenie", "data sporządzenia pierwszej deklaracji", OBOWIAZKOWY),
    Identyfikator("a11y-data-przeglad", "data ostatniego przeglądu deklaracji", WARUNKOWY,
                  "obowiązkowy od pierwszego przeglądu (przegląd co roku do 31 marca – art. 11)"),
    Identyfikator("a11y-kontakt", "imię i nazwisko osoby albo nazwa komórki do kontaktu", OBOWIAZKOWY),
    Identyfikator("a11y-email", "adres e-mail do kontaktu w sprawie dostępności", OBOWIAZKOWY),
    Identyfikator("a11y-telefon", "numer telefonu do kontaktu w sprawie dostępności", OBOWIAZKOWY),
    Identyfikator("a11y-procedura", "sekcja „Obsługa wniosków i skarg związanych z dostępnością”", OBOWIAZKOWY),
    Identyfikator("a11y-aplikacje", "sekcja „Aplikacje mobilne”", WARUNKOWY,
                  "tylko w deklaracji strony podmiotu, który ma aplikacje mobilne"),
    Identyfikator("a11y-architektura", "sekcja „Dostępność architektoniczna”", OBOWIAZKOWY),
    Identyfikator("a11y-architektura-url", "link do opisu dostępności architektonicznej", OPCJONALNY,
                  "gdy opis jest na osobnej stronie"),
    Identyfikator("a11y-komunikacja", "sekcja „Dostępność komunikacyjno-informacyjna”", OBOWIAZKOWY),
)

# Identyfikatory ze starszej wersji warunków (2019/2020). Spotykane na wielu stronach;
# walidator powinien je rozpoznawać i raportować jako „nieaktualna struktura”, a nie ignorować.
IDENTYFIKATORY_PRZESTARZALE: tuple[str, ...] = (
    "a11y-deklaracja",   # nagłówek z tytułem
    "a11y-osoba",        # zastąpiony przez a11y-kontakt
    "a11y-audytor",      # w wersji 2.0 brak osobnego identyfikatora
)

WSZYSTKIE_ZNANE_ID: frozenset[str] = frozenset(
    [i.id for i in IDENTYFIKATORY] + list(IDENTYFIKATORY_PRZESTARZALE)
)

OBOWIAZKOWE_ID: tuple[str, ...] = tuple(i.id for i in IDENTYFIKATORY if i.status == OBOWIAZKOWY)

# Śródtytuły, które warunki techniczne każą odwzorować wiernie.
# (tekst, czy_wymagany, uwaga)
NAGLOWKI: tuple[tuple[str, bool, str], ...] = (
    ("Deklaracja dostępności", True, "tytuł; h1 albo h2 zgodnie z hierarchią strony"),
    ("Stan dostępności cyfrowej", True, ""),
    ("Niedostępne treści", False, "wymagany przy stanie „częściowo zgodna” i „niezgodna”"),
    ("Przygotowanie deklaracji dostępności", True, "w przykładach MC także „… i jej aktualizacja”"),
    ("Udogodnienia, ograniczenia i inne informacje", False, "dobrowolny"),
    ("Skróty klawiszowe", False, "wymagany, gdy strona ma niestandardowe skróty"),
    ("Informacje zwrotne i dane kontaktowe", True, ""),
    ("Obsługa wniosków i skarg związanych z dostępnością", True, "section#a11y-procedura"),
    ("Pozostałe informacje", True, ""),
    ("Aplikacje mobilne", False, "section#a11y-aplikacje, gdy podmiot ma aplikacje"),
    ("Dostępność architektoniczna", True, "section#a11y-architektura"),
    ("Dostępność komunikacyjno-informacyjna", True, "section#a11y-komunikacja"),
)

# Początki formuł obowiązkowych (porównywać po normalizacji spacji i wielkości liter).
FORMULA_WSTEPU = "zobowiązuje się zapewnić dostępność swojej"
FORMULY_STATUSU: dict[str, str] = {
    "zgodna": "jest w pełni zgodna z załącznikiem do ustawy",
    "czesciowo_zgodna": "jest częściowo zgodna z załącznikiem do ustawy",
    "niezgodna": "jest niezgodna z załącznikiem do ustawy",
}

# Meta tag z adresem deklaracji – dobra praktyka z warunków technicznych (nie obowiązek).
META_NAZWY: tuple[str, ...] = ("deklaracja-dostępności", "deklaracja-dostepnosci")
