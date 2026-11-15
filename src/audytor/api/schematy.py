"""Schematy żądań i odpowiedzi REST API (Pydantic)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from audytor.crawler.links import normalize_url
from audytor.db import Skan, StatusSkanu


class NowySkan(BaseModel):
    """Zlecenie skanu. Sprint 1: sprawdzana jest jedna strona – `url`."""

    url: str = Field(examples=["https://www.wasilkow.pl/"], max_length=2048)
    parametry: dict[str, Any] = Field(
        default_factory=dict,
        description="Opcje skanu zapisywane razem z nim (np. limity crawlera od sprintu 3).",
    )

    @field_validator("url")
    @classmethod
    def _poprawny_adres(cls, url: str) -> str:
        znormalizowany = normalize_url(url)
        if znormalizowany is None:
            raise ValueError("wymagany adres strony WWW zaczynający się od http:// lub https://")
        return znormalizowany


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
    liczba_podstron: int
    liczba_problemow: int

    @classmethod
    def z_bazy(cls, skan: Skan) -> SkanOut:
        return cls(
            id=skan.id,
            url_startowy=skan.url_startowy,
            status=skan.status,
            utworzono=_utc(skan.utworzono),
            rozpoczeto=_utc(skan.rozpoczeto),
            zakonczono=_utc(skan.zakonczono),
            opis_bledu=skan.opis_bledu,
            parametry=dict(skan.parametry or {}),
            liczba_podstron=len(skan.podstrony),
            liczba_problemow=sum(len(p.problemy) for p in skan.podstrony),
        )


class WynikiSkanu(BaseModel):
    skan: SkanOut
    podstrony: list[dict[str, Any]] = Field(
        description="Wyniki podstron w formacie wynik.json (docs/kontrakt-danych.md, sekcja 2)."
    )


class Zdrowie(BaseModel):
    status: Literal["ok", "blad"]
    wersja: str
    baza: str
    kolejka: str
