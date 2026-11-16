"""`audytor-api` / `python -m audytor.api` – serwer API (uvicorn)."""

from __future__ import annotations

import argparse

import uvicorn


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="audytor-api", description="Uruchamia REST API audytora (FastAPI).")
    parser.add_argument("--host", default="127.0.0.1", help="adres nasłuchu (w Dockerze 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="przeładowanie po zmianie kodu (praca lokalna)")
    args = parser.parse_args(argv)
    uvicorn.run("audytor.api.app:create_app", factory=True, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
