# Jeden obraz dla API, workera i migracji (różnią się tylko komendą w docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Zależności i Chromium (Playwright) – wersja przeglądarki zawsze zgodna z zainstalowanym Playwrightem.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install . \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY alembic.ini ./
COPY migrations ./migrations

# Bez roota (Celery ostrzega przed uruchamianiem jako root).
RUN useradd --create-home audytor && mkdir -p /app/wyniki && chown audytor /app/wyniki
USER audytor

ENV AUDYTOR_WYNIKI_DIR=/app/wyniki
EXPOSE 8000
CMD ["audytor-api", "--host", "0.0.0.0", "--port", "8000"]
