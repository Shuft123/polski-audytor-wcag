"""Środowisko Alembic: adres bazy z AUDYTOR_DB_URL, metadane z audytor.db (do --autogenerate i check)."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from audytor.db import Base
from audytor.ustawienia import Ustawienia

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    # `alembic -x db=sqlite:///inna.db upgrade head` nadpisuje zmienną środowiskową.
    return context.get_x_argument(as_dictionary=True).get("db") or Ustawienia.ze_srodowiska().db_url


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql` – wypisuje SQL bez łączenia z bazą."""
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        # render_as_batch: ALTER TABLE w SQLite (praca lokalna) działa przez kopię tabeli.
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
