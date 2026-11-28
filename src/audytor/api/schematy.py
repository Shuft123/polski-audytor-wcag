"""Schematy żądań i odpowiedzi REST API (Pydantic)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from audytor.crawler.links import normalize_url
from audytor.db import Podstrona, Skan, StatusSkanu
from audytor.skan.lista import DOMYSLNIE_MAX_PODSTRON, LIMIT_PODSTRON, lista_podstron
from audytor.worker.kroki import NAZWY_KROKOW



class NowySkan(BaseModel):
    """Zlecenie skanu: strona startowa + opcjonalnie lista jej podstron (ta sama witryna)."""

    url: str = Field(examples=["https://www.wasilkow.pl/"], max_length=2048, description="Strona startowa.")
    podstrony: list[str] = Field(
        default_factory=list,
        max_length=500,
        examples=[["https://www.wasilkow.pl/kontakt", "https://www.wasilkow.pl/deklaracja-dostepnosci"]],
        description="Dodatkowe podstrony do sprawdzenia. Adresy z innej witryny są pomijane "
                    "(lista pominiętych: pole `uwagi` skanu).",
    )
    max_podstron: int = Field(
        DOMYSLNIE_MAX_PODSTRON, ge=1, le=LIMIT_PODSTRON,
        description=f"Najwyżej tyle podstron w skanie, licząc stronę startową (maks. {LIMIT_PODSTRON}).",
    )
    pomin_kroki: list[str] = Field(
        default_factory=list,
        examples=[["fokus"]],
        description=f"Kroki skanu do pominięcia: {', '.join(NAZWY_KROKOW)}.",
    )
    parametry: dict[str, Any] = Field(
        default_factory=dict,
        description="Dodatkowe opcje zapisywane razem ze skanem. Pola powyżej, jeśli podane, mają pierwszeństwo "
                    "przed tymi samymi kluczami tutaj.",
    )

    @field_validator("url")
    @classmethod
    def _poprawny_adres(cls, url: str) -> str:
        znormalizowany = normalize_url(url)
        if znormalizowany is None:
            raise ValueError("wymagany adres strony WWW zaczynający się od http:// lub https://")
        return znormalizowany

    @field_validator("podstrony")
    @classmethod
    def _poprawne_podstrony(cls, podstrony: list[str]) -> list[str]:
        zle = [u for u in podstrony if normalize_url(u) is None]
        if zle:
            raise ValueError(f"nieprawidłowe adresy podstron (wymagane http:// lub https://): {', '.join(zle[:5])}")
        return [normalize_url(u) for u in podstrony]

    @field_validator("pomin_kroki")
    @classmethod
    def _znane_kroki(cls, kroki: list[str]) -> list[str]:
        nieznane = sorted(set(kroki) - set(NAZWY_KROKOW))
        if nieznane:
            raise ValueError(f"nieznane kroki: {', '.join(nieznane)} (dostępne: {', '.join(NAZWY_KROKOW)})")
        return list(dict.fromkeys(kroki))

    def do_parametrow(self) -> dict[str, Any]:
        """Parametry zapisywane w skanie i czytane przez worker (`lista_podstron`, `pomin_kroki`).

        Pola podane jawnie mają pierwszeństwo przed tymi samymi kluczami w `parametry`; pola niepodane
        nie nadpisują `parametry` (zgodność z klientami ze sprintu 2, które wysyłają tylko `parametry`).
        """
        parametry = dict(self.parametry)
        podane = self.model_fields_set
        if "max_podstron" in podane or "max_podstron" not in parametry:
            parametry["max_podstron"] = self.max_podstron
        if "podstrony" in podane:
            parametry["podstrony"] = self.podstrony
        if "pomin_kroki" in podane:
            parametry["pomin_kroki"] = self.pomin_kroki
        for klucz in ("podstrony", "pomin_kroki"):
            if klucz in parametry and not parametry[klucz]:
                del parametry[klucz]
        return parametry


def _utc(czas: datetime | None) -> datetime | None:
    # Kontrakt: czasy w UTC. SQLite oddaje je bez strefy (zapisujemy UTC, więc brak strefy = UTC),
    # PostgreSQL – w strefie sesji (np. +01:00), więc przeliczamy.
    if czas is None:
        return None
    if czas.tzinfo is None:
        return czas.replace(tzinfo=timezone.utc)
    return czas.astimezone(timezone.utc)


class SkanOut(BaseModel):
    id: int
    url_startowy: str
    status: StatusSkanu
    utworzono: datetime
    rozpoczeto: datetime | None
    zakonczono: datetime | None
    opis_bledu: str | None
    parametry: dict[str, Any]
    planowane_podstrony: int = Field(description="Ile podstron skan sprawdzi (strona startowa + podane, po limicie).")
    liczba_podstron: int = Field(description="Ile podstron już przetworzono (także z błędem) – postęp skanu.")
    podstrony_z_bledem: int
    liczba_problemow: int
    uwagi: list[str] = Field(description="Pominięte adresy podstron i powód (inna witryna, ponad limit).")

    @classmethod
    def z_bazy(cls, skan: Skan) -> SkanOut:
        parametry = dict(skan.parametry or {})
        lista = lista_podstron(skan.url_startowy, parametry)
        return cls(
            id=skan.id,
            url_startowy=skan.url_startowy,
            status=skan.status,
            utworzono=_utc(skan.utworzono),
            rozpoczeto=_utc(skan.rozpoczeto),
            zakonczono=_utc(skan.zakonczono),
            opis_bledu=skan.opis_bledu,
            parametry=parametry,
            planowane_podstrony=len(lista.adresy),
            liczba_podstron=len(skan.podstrony),
            podstrony_z_bledem=sum(1 for p in skan.podstrony if p.blad),
            liczba_problemow=sum(len(p.problemy) for p in skan.podstrony),
            uwagi=lista.pominiete,
        )


class PodstronaOut(BaseModel):
    """Skrót podstrony skanu – lista do dashboardu; szczegóły w GET /skany/{id}/wyniki."""

    id: int
    url: str
    requested_url: str
    http_status: int | None
    sprawdzono: datetime
    blad: str | None
    liczba_problemow: int
    ostrzezenia: list[str]
    test_fokusu: bool = Field(description="Czy dla podstrony wykonano test fokusu.")
    zrzut: str | None = Field(description="Ścieżka API do zrzutu ekranu podstrony (None – brak zrzutu).")
    mapa_fokusu: str | None = Field(description="Ścieżka API do mapy kolejności fokusu (None – brak).")

    @classmethod
    def z_bazy(cls, podstrona: Podstrona, zrzut: str | None, mapa_fokusu: str | None) -> PodstronaOut:
        return cls(
            id=podstrona.id,
            url=podstrona.url,
            requested_url=podstrona.requested_url,
            http_status=podstrona.http_status,
            sprawdzono=_utc(podstrona.sprawdzono),
            blad=podstrona.blad,
            liczba_problemow=len(podstrona.problemy),
            ostrzezenia=list(podstrona.ostrzezenia or []),
            test_fokusu=podstrona.fokus is not None,
            zrzut=zrzut,
            mapa_fokusu=mapa_fokusu,
        )


class WynikiSkanu(BaseModel):
    skan: SkanOut
    podstrony: list[dict[str, Any]] = Field(
        description="Wyniki podstron w formacie wynik.json (docs/kontrakt-danych.md, sekcja 2) oraz: `id` "
                    "podstrony, `fokus` – wynik testu fokusu albo null, `zrzut` – ścieżka API do zrzutu ekranu."
    )
    deklaracja: dict[str, Any] | None = Field(
        description="Wynik wyszukania i walidacji deklaracji dostępności witryny (null – nie sprawdzano)."
    )


class Zdrowie(BaseModel):
    status: Literal["ok", "blad"]
    wersja: str
    baza: str
    kolejka: str
