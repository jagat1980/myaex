"""PostgreSQL store operations for entity resolution aliases and conflicts."""

import json
import logging
from typing import Any
import uuid
import asyncpg
from connectors.common.models import NormalisedRecord

logger = logging.getLogger("resolver.store")


class AliasStore:
    """Manages ci_alias lookups, upserts, and conflict queue in PostgreSQL."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn

    async def load_existing_aliases(self, tenant_id: str) -> dict[str, uuid.UUID]:
        """Fetch all existing source_id -> ci_id mappings for a tenant."""
        rows = await self.conn.fetch(
            """
            SELECT source_system, source_id, ci_id
            FROM ci_alias
            WHERE tenant_id = $1;
            """,
            tenant_id,
        )
        aliases: dict[str, uuid.UUID] = {}
        for row in rows:
            key = f"{row['source_system']}:{row['source_id']}"
            aliases[key] = uuid.UUID(str(row["ci_id"]))
        return aliases

    async def upsert_ci_alias(
        self,
        tenant_id: str,
        source_system: str,
        source_id: str,
        ci_id: uuid.UUID,
        confidence: float,
    ) -> None:
        """Insert or update a canonical identity mapping."""
        await self.conn.execute(
            """
            INSERT INTO ci_alias (tenant_id, source_system, source_id, ci_id, confidence, last_verified)
            VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP)
            ON CONFLICT (tenant_id, source_system, source_id)
            DO UPDATE SET
                ci_id = EXCLUDED.ci_id,
                confidence = EXCLUDED.confidence,
                last_verified = CURRENT_TIMESTAMP;
            """,
            tenant_id,
            source_system,
            source_id,
            ci_id,
            confidence,
        )

    async def record_conflict(
        self,
        tenant_id: str,
        ci_id_candidate: uuid.UUID | None,
        source_system: str,
        source_id: str,
        conflict_reason: str,
        raw_payload: dict[str, Any],
    ) -> None:
        """Route an ambiguous resolution candidate to er_conflicts review queue."""
        json_payload = json.dumps(raw_payload, sort_keys=True, default=str)
        await self.conn.execute(
            """
            INSERT INTO er_conflicts (
                tenant_id, ci_id_candidate, source_system, source_id, conflict_reason, raw_payload
            ) VALUES ($1, $2, $3, $4, $5, $6);
            """,
            tenant_id,
            ci_id_candidate,
            source_system,
            source_id,
            conflict_reason,
            json_payload,
        )
        logger.warning(
            "Recorded ER conflict for %s:%s (reason: %s)",
            source_system,
            source_id,
            conflict_reason,
        )

    async def fetch_latest_raw_records(self, tenant_id: str) -> list[dict[str, Any]]:
        """Fetch the latest payload for each distinct (source_system, source_id)."""
        rows = await self.conn.fetch(
            """
            SELECT DISTINCT ON (source_system, source_id)
                source_system, source_id, kind, payload, observed_at
            FROM raw_records
            WHERE tenant_id = $1
            ORDER BY source_system, source_id, observed_at DESC;
            """,
            tenant_id,
        )
        return [dict(r) for r in rows]
