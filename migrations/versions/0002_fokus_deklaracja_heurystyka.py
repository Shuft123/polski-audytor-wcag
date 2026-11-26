"""Sprint 2: wyniki testu fokusu i deklaracji, źródło „heurystyka”, błąd podstrony (F7).

- `wynik_fokusu` – pełny wynik testu fokusu podstrony (F8, osoba 4), 1:1 z `podstrona`,
- `wynik_deklaracji` – wynik wyszukania i walidacji deklaracji dostępności (F17/F18, osoba 5), 1:1 ze `skan`,
- `podstrona.blad` – podstrona, której nie udało się sprawdzić (robots.txt, timeout) przy skanie wielu podstron,
- `problem.zrodlo` – nowa wartość "heurystyka" (reguły bez modelu AI: fokus, deklaracja, tryb AI bez modelu).

Opis i diagram: docs/model-danych.md. Zmiany ograniczenia CHECK autogenerate nie wykrywa – są dopisane ręcznie.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

ZRODLA_V1 = ("axe", "ai")
ZRODLA_V2 = ("axe", "ai", "heurystyka")


def _check_zrodla(zrodla: tuple[str, ...]) -> str:
    return "zrodlo IN (" + ", ".join(f"'{z}'" for z in zrodla) + ")"


def upgrade() -> None:
    with op.batch_alter_table("podstrona") as batch:
        batch.add_column(sa.Column("blad", sa.Text(), nullable=True))

    # Ograniczenie CHECK „zrodlo_problemu” (Enum z native_enum=False) – podmiana na listę z "heurystyka".
    with op.batch_alter_table("problem") as batch:
        batch.drop_constraint("zrodlo_problemu", type_="check")
        batch.create_check_constraint("zrodlo_problemu", _check_zrodla(ZRODLA_V2))

    op.create_table(
        "wynik_fokusu",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("podstrona_id", sa.Integer(), nullable=False),
        sa.Column("sprawdzono", sa.DateTime(timezone=True), nullable=False),
        sa.Column("zakonczenie", sa.Text(), nullable=False),
        sa.Column("limit_krokow", sa.Integer(), nullable=True),
        sa.Column("podsumowanie", JSON, nullable=False),
        sa.Column("kroki", JSON, nullable=False),
        sa.Column("ostrzezenia", JSON, nullable=False),
        sa.Column("mapa", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["podstrona_id"], ["podstrona.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wynik_fokusu_podstrona_id", "wynik_fokusu", ["podstrona_id"], unique=True)

    op.create_table(
        "wynik_deklaracji",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("skan_id", sa.Integer(), nullable=False),
        sa.Column("sprawdzono", sa.DateTime(timezone=True), nullable=False),
        sa.Column("znaleziono", sa.Boolean(), nullable=False),
        sa.Column("url_deklaracji", sa.String(length=2048), nullable=True),
        sa.Column("metoda", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("pewnosc", sa.Float(), nullable=False),
        sa.Column("zweryfikowano", sa.Boolean(), nullable=False),
        sa.Column("identyfikatory_a11y", JSON, nullable=False),
        sa.Column("brakujace_identyfikatory", JSON, nullable=False),
        sa.Column("kandydaci", JSON, nullable=False),
        sa.Column("ostrzezenia", JSON, nullable=False),
        sa.Column("walidacja", JSON, nullable=True),
        sa.ForeignKeyConstraint(["skan_id"], ["skan.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wynik_deklaracji_skan_id", "wynik_deklaracji", ["skan_id"], unique=True)


def downgrade() -> None:
    op.drop_table("wynik_deklaracji")     # indeksy znikają razem z tabelą
    op.drop_table("wynik_fokusu")

    # W wersji 0001 nie ma źródła "heurystyka" – wtedy test fokusu zapisywał się jako "ai".
    op.execute("UPDATE problem SET zrodlo = 'ai' WHERE zrodlo = 'heurystyka'")
    with op.batch_alter_table("problem") as batch:
        batch.drop_constraint("zrodlo_problemu", type_="check")
        batch.create_check_constraint("zrodlo_problemu", _check_zrodla(ZRODLA_V1))

    with op.batch_alter_table("podstrona") as batch:
        batch.drop_column("blad")
