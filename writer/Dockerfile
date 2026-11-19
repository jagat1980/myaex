# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install runtime dependencies
RUN pip install --no-cache-dir \
    "pydantic>=2.7.0" \
    "asyncpg>=0.29.0" \
    "neo4j>=5.19.0"

# Create unprivileged non-root user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -d /app appuser

# Copy application packages
COPY connectors /app/connectors
COPY resolver /app/resolver
COPY writer /app/writer

USER 10001:10001

ENTRYPOINT ["python", "-m", "writer.main"]
