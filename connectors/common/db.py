"""Database operations for Context Graph raw storage and ingest run telemetry."""

from datetime import datetime, timezone
import json
import os
from typing import Any
import asyncpg
from connectors.common.hasher import compute_content_hash
from connectors.common.models import IngestRunResult


def get_db_connection_params() -> dict[str, Any]:
    """Retrieve PostgreSQL connection parameters from environment or secret mount."""
    auth_json_raw = os.getenv("POSTGRES_AUTH_JSON")
    auth_file_path = os.getenv("POSTGRES_AUTH_FILE", "/mnt/secrets-store/postgres-auth")

    if not auth_json_raw and os.path.exists(auth_file_path):
        try:
            with open(auth_file_path, "r", encoding="utf-8") as f:
                auth_json_raw = f.read().strip()
        except Exception:
            pass

    if auth_json_raw:
        try:
            parsed = json.loads(auth_json_raw)
            return {
                "host": parsed.get("host", "localhost"),
                "port": int(parsed.get("port", 5432)),
                "user": parsed.get("username", "cgadmin"),
                "password": parsed.get("password", ""),
                "database": parsed.get("database", "contextgraph"),
                "ssl": "require",
            }
        except json.JSONDecodeError:
            pass

    return {
        "host": os.getenv("PGHOST", "localhost"),
        "port": int(os.getenv("PGPORT", "5432")),
        "user": os.getenv("PGUSER", "cgadmin"),
        "password": os.getenv("PGPASSWORD", ""),
        "database": os.getenv("PGDATABASE", "contextgraph"),
        "ssl": os.getenv("PGSSLMODE", "require"),
    }


async def create_db_pool() -> asyncpg.Pool:
    """Create an asynchronous connection pool to PostgreSQL."""
    params = get_db_connection_params()
    return await asyncpg.create_pool(
        host=params["host"],
        port=params["port"],
        user=params["user"],
        password=params["password"],
        database=params["database"],
        ssl=params["ssl"],
        min_size=1,
        max_size=5,
    )


async def upsert_raw_record(
    conn: asyncpg.Connection,
    tenant_id: str,
    source_system: str,
    source_id: str,
    kind: str,
    payload: dict[str, Any] | list[Any],
    observed_at: datetime,
) -> bool:
    """Insert raw payload if content hash has changed or is new.

    Returns True if a new record was inserted, False if it was an identical duplicate.
    """
    content_hash = compute_content_hash(payload)
    json_payload = json.dumps(payload, sort_keys=True, default=str)

    # Check if this exact payload was already recorded
    row = await conn.fetchrow(
        """
        INSERT INTO raw_records (
            tenant_id, source_system, source_id, kind, payload, content_hash, observed_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (tenant_id, source_system, source_id, content_hash) DO NOTHING
        RETURNING id;
        """,
        tenant_id,
        source_system,
        source_id,
        kind,
        json_payload,
        content_hash,
        observed_at,
    )
    return row is not None


async def start_ingest_run(
    conn: asyncpg.Connection,
    tenant_id: str,
    source_system: str,
) -> int:
    """Record the start of an ingestion cycle in ingest_runs."""
    started_at = datetime.now(timezone.utc)
    row = await conn.fetchrow(
        """
        INSERT INTO ingest_runs (
            tenant_id, source_system, started_at, status
        ) VALUES ($1, $2, $3, 'RUNNING')
        RETURNING id;
        """,
        tenant_id,
        source_system,
        started_at,
    )
    return int(row["id"])


async def finish_ingest_run(
    conn: asyncpg.Connection,
    run_id: int,
    result: IngestRunResult,
) -> None:
    """Finalize an ingestion run with counts, watermark, and status."""
    finished_at = datetime.now(timezone.utc)
    await conn.execute(
        """
        UPDATE ingest_runs
        SET watermark = $1,
            records_read = $2,
            records_new = $3,
            records_changed = $4,
            errors = $5,
            finished_at = $6,
            status = $7
        WHERE id = $8;
        """,
        result.watermark,
        result.records_read,
        result.records_new,
        result.records_changed,
        result.errors,
        finished_at,
        result.status,
        run_id,
    )
