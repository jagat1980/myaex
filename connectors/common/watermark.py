"""Incremental watermark management for connector ingestion runs."""

from datetime import datetime, timezone
import asyncpg


async def get_latest_watermark(
    conn: asyncpg.Connection,
    tenant_id: str,
    source_system: str,
) -> str | None:
    """Fetch the latest successful watermark for a tenant and source system."""
    row = await conn.fetchrow(
        """
        SELECT watermark 
        FROM ingest_runs 
        WHERE tenant_id = $1 
          AND source_system = $2 
          AND status = 'SUCCESS'
          AND watermark IS NOT NULL
        ORDER BY started_at DESC 
        LIMIT 1;
        """,
        tenant_id,
        source_system,
    )
    if row and row["watermark"]:
        return str(row["watermark"])
    return None


def format_iso_watermark(dt: datetime | None = None) -> str:
    """Format a datetime as an ISO 8601 UTC watermark string."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
