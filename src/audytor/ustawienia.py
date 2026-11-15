"""Ustawienia usługi (API i worker) czytane ze zmiennych środowiskowych.

| Zmienna                 | Domyślnie                     | Znaczenie                                        |
|-------------------------|-------------------------------|--------------------------------------------------|
| AUDYTOR_DB_URL          | sqlite:///audytor.db          | adres bazy (SQLAlchemy), w Dockerze PostgreSQL   |
| AUDYTOR_REDIS_URL       | redis://localhost:6379/0      | broker kolejki Celery                            |
| AUDYTOR_WYNIKI_DIR      | wyniki                        | folder na migawki i wynik.json ze skanów         |
| AUDYTOR_PRZEGLADARKA    | (puste = Chromium Playwrighta)| "chrome" / "msedge" – przeglądarka z systemu     |
| AUDYTOR_TIMEOUT_S       | 30                            | limit wczytania strony w sekundach               |

Lokalnie można je wpisać do pliku `.env` (wzór: `.env.example`) – docker-compose czyta go sam.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Ustawienia:
    db_url: str = "sqlite:///audytor.db"
    redis_url: str = "redis://localhost:6379/0"
    wyniki_dir: Path = Path("wyniki")
    przegladarka: str | None = None
    timeout_s: float = 30.0

    @classmethod
    def ze_srodowiska(cls) -> Ustawienia:
        env = os.environ
        return cls(
            db_url=env.get("AUDYTOR_DB_URL") or cls.db_url,
            redis_url=env.get("AUDYTOR_REDIS_URL") or cls.redis_url,
            wyniki_dir=Path(env.get("AUDYTOR_WYNIKI_DIR") or cls.wyniki_dir),
            przegladarka=env.get("AUDYTOR_PRZEGLADARKA") or None,
            timeout_s=float(env.get("AUDYTOR_TIMEOUT_S") or cls.timeout_s),
        )
