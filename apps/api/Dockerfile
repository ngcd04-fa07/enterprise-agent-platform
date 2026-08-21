FROM python:3.12-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir .

EXPOSE 8000

# Migrations run on container start, not as a separate step: this is a
# single-instance dev/demo deployment, so there's no multi-replica race to
# worry about. A real multi-replica production deployment would need this
# to be a separate release step instead (see docs/architecture.md) —
# revisit at Stage 21.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
