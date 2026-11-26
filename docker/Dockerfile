FROM python:3.12-slim-bookworm AS builder

RUN pip install --no-cache-dir uv==0.13.10

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY README.md LICENSE ./
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini ./


RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd --system hookflow \
    && useradd --system --gid hookflow --home-dir /app --shell /usr/sbin/nologin hookflow

WORKDIR /app

COPY --from=builder --chown=hookflow:hookflow /app/.venv /app/.venv
COPY --from=builder --chown=hookflow:hookflow /app/migrations /app/migrations
COPY --from=builder --chown=hookflow:hookflow /app/alembic.ini /app/alembic.ini

EXPOSE 8000

USER hookflow

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
