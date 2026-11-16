"""REST API (F21, osoba 6): FastAPI nad bazą wyników i kolejką skanów.

    audytor-api --reload              # http://localhost:8000/docs
"""

from .app import create_app

__all__ = ["create_app"]
