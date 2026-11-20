# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH="/app/mcp:/app"

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install runtime dependencies
RUN pip install --no-cache-dir \
    "fastmcp>=0.1.0" \
    "mcp>=1.0.0" \
    "uvicorn>=0.30.0" \
    "starlette>=0.38.0" \
    "pydantic>=2.7.0" \
    "asyncpg>=0.29.0" \
    "neo4j>=5.19.0" \
    "opentelemetry-api>=1.28.0"

# Create unprivileged non-root user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -d /app appuser

# Copy application packages
COPY mcp /app/mcp
COPY resolver /app/resolver
COPY writer /app/writer
COPY risk /app/risk

USER 10001:10001

EXPOSE 3001

ENTRYPOINT ["python", "-m", "context_graph.server"]
