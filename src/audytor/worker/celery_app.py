"""Aplikacja Celery – kolejka skanów (szkielet, sprint 1; pełna kolejka F4 – sprint 3).

Uruchomienie workera (Redis musi działać, np. z docker-compose):
    celery -A audytor.worker worker --loglevel=info --concurrency=2

API nie importuje kodu zadań (ani Playwrighta) – wysyła zadanie po nazwie (`ZADANIE_SKANU`).
"""

from __future__ import annotations

from celery import Celery

from audytor.ustawienia import Ustawienia

ZADANIE_SKANU = "audytor.skanuj_strone"


def utworz_celery(ustawienia: Ustawienia | None = None) -> Celery:
    ustawienia = ustawienia or Ustawienia.ze_srodowiska()
    app = Celery("audytor", broker=ustawienia.redis_url, include=["audytor.worker.zadania"])
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        task_ignore_result=True,          # stan skanu trzymamy w bazie (tabela skan), nie w Celery
        task_acks_late=True,              # zadanie wraca do kolejki, gdy worker padnie w trakcie skanu
        worker_prefetch_multiplier=1,     # skan trwa długo – worker bierze po jednym
        task_soft_time_limit=540,         # 9 min: SoftTimeLimitExceeded -> skan oznaczony jako błąd
        task_time_limit=600,
        broker_connection_retry_on_startup=True,
        broker_connection_timeout=3,
        # API nie może wisieć, gdy Redis nie działa – szybko zgłaszamy błąd.
        task_publish_retry_policy={"max_retries": 2, "interval_start": 0, "interval_step": 0.5, "interval_max": 1},
        timezone="UTC",
    )
    return app


app = utworz_celery()
