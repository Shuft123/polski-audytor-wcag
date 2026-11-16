"""Worker Celery (osoba 6): wykonuje skany zlecone przez API.

    celery -A audytor.worker worker --loglevel=info

Publiczne API:
    app, ZADANIE_SKANU    – aplikacja Celery i nazwa zadania skanu (celery_app.py)
    wykonaj_skan(...)     – właściwa logika zadania, do wywołania także bez Celery (zadania.py)
"""

from .celery_app import ZADANIE_SKANU, app

__all__ = ["ZADANIE_SKANU", "app"]
