"""Audit logging module for Context Graph MCP server.

Enforces Skill Requirement 5:
Audit every tool call to PostgreSQL audit_log table
(caller, tool, args hash, result count, latency).
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Dict, Optional
import asyncpg

logger = logging.getLogger(__name__)

# Global or injected asyncpg pool for audit logging
_audit_pool: Optional[asyncpg.Pool] = None


def set_audit_pool(pool: Optional[asyncpg.Pool]) -> None:
    """Set the global database pool for audit logging."""
    global _audit_pool
    _audit_pool = pool


def hash_arguments(args: Dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of tool arguments."""
    try:
        serialized = json.dumps(args, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    except Exception:
        return hashlib.sha256(str(args).encode("utf-8")).hexdigest()


async def record_audit_log(
    tenant_id: str,
    actor: str,
    tool_name: str,
    entity_id: str,
    args: Dict[str, Any],
    result_count: int,
    latency_ms: float,
    pool: Optional[asyncpg.Pool] = None,
) -> None:
    """Record a tool invocation to PostgreSQL audit_log table and structured logger."""
    db_pool = pool or _audit_pool
    args_hash = hash_arguments(args)

    details = {
        "args_hash": args_hash,
        "result_count": result_count,
        "latency_ms": round(latency_ms, 2),
    }

    # Structured JSON log
    logger.info(
        "AUDIT: tenant=%s actor=%s tool=%s entity=%s latency_ms=%.2f results=%d",
        tenant_id,
        actor,
        tool_name,
        entity_id,
        latency_ms,
        result_count,
    )

    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO audit_log (tenant_id, actor, action, entity_type, entity_id, details, timestamp)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    tenant_id,
                    actor,
                    tool_name,
                    "tool_call",
                    entity_id[:256],
                    json.dumps(details),
                    datetime.now(timezone.utc),
                )
        except Exception as e:
            logger.warning("Failed to persist audit log to PostgreSQL: %s", e)
