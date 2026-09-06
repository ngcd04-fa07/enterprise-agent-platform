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

# Stage 21: migrations no longer run here — see docker-compose.yml's
# `migrate` service, which runs `alembic upgrade head` exactly once as
# its own short-lived container, with `api` waiting for it to complete
# successfully before starting. This image still supports being invoked
# directly with `alembic upgrade head` as its command (that's exactly
# what the `migrate` service does), so nothing here is migrate-specific;
# this default CMD is just what runs when no other command is given.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
