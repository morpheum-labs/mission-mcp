FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends bash \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
COPY src /app/src

RUN pip install --no-cache-dir pip -U \
    && pip install --no-cache-dir -e /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
