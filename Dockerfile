# syntax=docker/dockerfile:1
# Qistas — single-stage image for dev + CI parity (docs/adr/0023).
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.dev

# System deps: gettext (compilemessages), libmagic (future file validation),
# curl (fetch Tailwind CLI), postgres client libs are provided by psycopg[binary].
RUN apt-get update && apt-get install -y --no-install-recommends \
        gettext \
        libmagic1 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for layer caching.
COPY pyproject.toml README.md ./
RUN pip install -e ".[dev]"

# Fetch the Tailwind standalone CLI (not committed — see docs/adr/0024).
COPY scripts/fetch-tailwind.sh ./scripts/fetch-tailwind.sh
RUN chmod +x scripts/fetch-tailwind.sh && ./scripts/fetch-tailwind.sh

# App source.
COPY . .

# Build CSS + collect static (safe to run at build; re-run in entrypoint for dev).
RUN ./bin/tailwindcss -i static/src/app.css -o static/css/app.css --minify || \
    echo "WARN: Tailwind build skipped (offline?); run 'make css' later"

RUN chmod +x scripts/entrypoint.sh

# Non-root.
RUN useradd --create-home --uid 1000 qistas && chown -R qistas:qistas /app
USER qistas

EXPOSE 8000
ENTRYPOINT ["./scripts/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
