"""Model danych v1: skan -> podstrona -> problem (F7, docs/model-danych.md).

Odtwarza dokładnie tabele z src/audytor/db/models.py w stanie ze sprintu 1. Wygenerowane przez
`alembic revision --autogenerate` na PostgreSQL i uporządkowane ręcznie; zgodność z modelami
sprawdza w CI `alembic check`.

Revision ID: 0001
Revises: –
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Listy JSON: w PostgreSQL JSONB (indeksowalne), w SQLite zwykły JSON.
JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _enum(nazwa: str, *wartosci: str) -> sa.Enum:
    # Tekst + CHECK zamiast natywnego ENUM – nowa wartość nie wymaga ALTER TYPE (decyzja z model-danych.md).
    return sa.Enum(*wartosci, name=nazwa, native_enum=False, create_constraint=True, length=20)


def upgrade() -> None:
    op.create_table(
        "skan",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("url_startowy", sa.String(length=2048), nullable=False),
        sa.Column("status", _enum("status_skanu", "oczekuje", "w_trakcie", "zakonczony", "blad"), nullable=False),
        sa.Column("utworzono", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rozpoczeto", sa.DateTime(timezone=True), nullable=True),
        sa.Column("zakonczono", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opis_bledu", sa.Text(), nullable=True),
        sa.Column("parametry", JSON, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "podstrona",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("skan_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("requested_url", sa.String(length=2048), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("sprawdzono", sa.DateTime(timezone=True), nullable=False),
        sa.Column("migawka", sa.String(length=255), nullable=True),
        sa.Column("narzedzia", JSON, nullable=False),
        sa.Column("ostrzezenia", JSON, nullable=False),
        sa.ForeignKeyConstraint(["skan_id"], ["skan.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skan_id", "url", name="uq_podstrona_skan_url"),
    )
    op.create_index("ix_podstrona_skan_id", "podstrona", ["skan_id"])

    op.create_table(
        "problem",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("podstrona_id", sa.Integer(), nullable=False),
        sa.Column("klucz", sa.String(length=32), nullable=False),
        sa.Column("zrodlo", _enum("zrodlo_problemu", "axe", "ai"), nullable=False),
        sa.Column("regula", sa.String(length=100), nullable=False),
        sa.Column("kryteria_wcag", JSON, nullable=False),
        sa.Column("poziom_wcag", sa.String(length=3), nullable=True),
        sa.Column("status", _enum("status_problemu", "blad", "do_weryfikacji", "odrzucony"), nullable=False),
        sa.Column("waga", _enum("waga_problemu", "krytyczna", "powazna", "umiarkowana", "drobna"), nullable=True),
        sa.Column("selektor", sa.Text(), nullable=False),
        sa.Column("fragment_html", sa.Text(), nullable=False),
        sa.Column("opis", sa.Text(), nullable=False),
        sa.Column("szczegoly", sa.Text(), nullable=False),
        sa.Column("link_pomocy", sa.String(length=2048), nullable=True),
        sa.Column("poziom_pewnosci", sa.Float(), nullable=True),
        sa.Column("uzasadnienie", sa.Text(), nullable=True),
        sa.Column("wykryto", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["podstrona_id"], ["podstrona.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("podstrona_id", "klucz", name="uq_problem_podstrona_klucz"),
    )
    op.create_index("ix_problem_podstrona_id", "problem", ["podstrona_id"])
    op.create_index("ix_problem_klucz", "problem", ["klucz"])
    op.create_index("ix_problem_regula", "problem", ["regula"])
    op.create_index("ix_problem_status", "problem", ["status"])


def downgrade() -> None:
    op.drop_table("problem")      # indeksy znikają razem z tabelą
    op.drop_table("podstrona")
    op.drop_table("skan")
