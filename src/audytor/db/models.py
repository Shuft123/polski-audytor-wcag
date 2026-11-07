"""Model danych v1 (F7): skan -> podstrona -> problem. Diagram ERD: docs/model-danych.md.

Modele są przenośne między PostgreSQL (docelowo, docker-compose osoby 6) i SQLite (testy, praca
lokalna): wartości wyliczeniowe trzymamy jako tekst z ograniczeniem CHECK, listy jako JSON.
Migracje (Alembic) dodajemy razem z osobą 6 – do tego czasu tabele tworzy `utworz_tabele()`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from audytor.wyniki import Status, Waga, Zrodlo


class StatusSkanu(StrEnum):
    """Stan skanu w kolejce (F4)."""

    OCZEKUJE = "oczekuje"
    W_TRAKCIE = "w_trakcie"
    ZAKONCZONY = "zakonczony"
    BLAD = "blad"


def _enum(klasa: type[StrEnum], nazwa: str) -> Enum:
    # Zapisujemy wartości ("blad"), a nie nazwy (BLAD); bez natywnego typu ENUM w PostgreSQL,
    # żeby dodanie nowej wartości nie wymagało ALTER TYPE.
    return Enum(
        klasa,
        name=nazwa,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda k: [e.value for e in k],
        validate_strings=True,
    )


# W PostgreSQL JSONB (da się po nim szukać i indeksować, np. problemy wg kryterium WCAG), w SQLite JSON.
_JSON = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: _JSON, list[str]: _JSON}


class Skan(Base):
    """Jedno zlecenie skanu witryny (z API, kolejki albo wiersza poleceń)."""

    __tablename__ = "skan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url_startowy: Mapped[str] = mapped_column(String(2048))
    status: Mapped[StatusSkanu] = mapped_column(_enum(StatusSkanu, "status_skanu"), default=StatusSkanu.OCZEKUJE)
    utworzono: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    rozpoczeto: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    zakonczono: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opis_bledu: Mapped[str | None] = mapped_column(Text)
    parametry: Mapped[dict[str, Any]] = mapped_column(default=dict)   # limity, opcje crawlera itd.

    podstrony: Mapped[list[Podstrona]] = relationship(
        back_populates="skan", cascade="all, delete-orphan", order_by="Podstrona.id"
    )

    def __repr__(self) -> str:
        return f"<Skan #{self.id} {self.url_startowy} {self.status}>"


class Podstrona(Base):
    """Jedna sprawdzona podstrona w ramach skanu."""

    __tablename__ = "podstrona"
    __table_args__ = (UniqueConstraint("skan_id", "url", name="uq_podstrona_skan_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skan_id: Mapped[int] = mapped_column(ForeignKey("skan.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(2048))              # final_url
    requested_url: Mapped[str] = mapped_column(String(2048))
    http_status: Mapped[int | None]
    sprawdzono: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    migawka: Mapped[str | None] = mapped_column(String(255))    # folder migawki (dom.html, zrzut, meta.json)
    narzedzia: Mapped[dict[str, Any]] = mapped_column(default=dict)
    ostrzezenia: Mapped[list[str]] = mapped_column(default=list)

    skan: Mapped[Skan] = relationship(back_populates="podstrony")
    problemy: Mapped[list[Problem]] = relationship(
        back_populates="podstrona", cascade="all, delete-orphan", order_by="Problem.id"
    )

    def __repr__(self) -> str:
        return f"<Podstrona #{self.id} {self.url}>"


class Problem(Base):
    """Jeden wykryty problem – te same pola co `audytor.wyniki.Problem` (kontrakt, sekcja 2)."""

    __tablename__ = "problem"
    __table_args__ = (UniqueConstraint("podstrona_id", "klucz", name="uq_problem_podstrona_klucz"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    podstrona_id: Mapped[int] = mapped_column(ForeignKey("podstrona.id", ondelete="CASCADE"), index=True)
    klucz: Mapped[str] = mapped_column(String(32), index=True)  # stały id z formatu wyniku (ten sam między skanami)
    zrodlo: Mapped[Zrodlo] = mapped_column(_enum(Zrodlo, "zrodlo_problemu"))
    regula: Mapped[str] = mapped_column(String(100), index=True)
    kryteria_wcag: Mapped[list[str]] = mapped_column(default=list)
    poziom_wcag: Mapped[str | None] = mapped_column(String(3))
    status: Mapped[Status] = mapped_column(_enum(Status, "status_problemu"), index=True)
    waga: Mapped[Waga | None] = mapped_column(_enum(Waga, "waga_problemu"))
    selektor: Mapped[str] = mapped_column(Text, default="")
    fragment_html: Mapped[str] = mapped_column(Text, default="")
    opis: Mapped[str] = mapped_column(Text, default="")
    szczegoly: Mapped[str] = mapped_column(Text, default="")
    link_pomocy: Mapped[str | None] = mapped_column(String(2048))
    poziom_pewnosci: Mapped[float | None] = mapped_column(Float)
    uzasadnienie: Mapped[str | None] = mapped_column(Text)
    wykryto: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    podstrona: Mapped[Podstrona] = relationship(back_populates="problemy")

    def __repr__(self) -> str:
        return f"<Problem #{self.id} {self.zrodlo}:{self.regula} {self.status}>"
