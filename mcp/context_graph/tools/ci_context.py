"""Tool: get_ci_context

Retrieves comprehensive metadata, environment tier, supporting business service,
operational ownership, and freshness confidence for a given Configuration Item.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
from neo4j import AsyncDriver, AsyncSession

logger = logging.getLogger(__name__)

CYPHER_GET_CI_CONTEXT = """
MATCH (c:CI)
WHERE (c.uid = $uid OR c.name = $ci) AND c.tenant_id = $tenant_id
OPTIONAL MATCH (c)-[:SUPPORTS]->(s:BusinessService)
OPTIONAL MATCH (c)-[:OWNED_BY]->(g:AssignmentGroup)
RETURN c.uid AS uid,
       c.name AS name,
       labels(c) AS labels,
       c.type AS type,
       c.env AS env,
       c.tier AS tier,
       c.confidence AS confidence,
       c.stale AS stale,
       c.last_seen AS last_seen,
       c.source_system AS source_system,
       s.name AS service_name,
       s.tier AS service_tier,
       g.name AS owner_group
LIMIT 1
"""


async def execute_get_ci_context(
    driver: AsyncDriver,
    tenant_id: str,
    ci: str,
) -> Dict[str, Any]:
    """Execute parameterized get_ci_context read transaction."""
    uid = f"{tenant_id}:{ci}" if ":" not in ci else ci

    async with driver.session() as session:
        result = await session.execute_read(
            _read_ci_context,
            tenant_id=tenant_id,
            ci=ci,
            uid=uid,
        )
        return result


async def _read_ci_context(
    tx: Any,
    tenant_id: str,
    ci: str,
    uid: str,
) -> Dict[str, Any]:
    cursor = await tx.run(CYPHER_GET_CI_CONTEXT, tenant_id=tenant_id, ci=ci, uid=uid)
    record = await cursor.single()
    if not record:
        return {
            "found": False,
            "ci": ci,
            "tenant_id": tenant_id,
            "message": f"Configuration Item '{ci}' not found in estate graph for tenant '{tenant_id}'.",
        }

    last_seen_str = str(record["last_seen"]) if record["last_seen"] else datetime.now(timezone.utc).isoformat()
    source_sys = record["source_system"] or "azure"
    ci_type = record["type"] or ([lbl for lbl in record["labels"] if lbl != "CI"] or ["VM"])[0]

    return {
        "found": True,
        "ci_id": record["uid"],
        "name": record["name"],
        "type": {
            "value": ci_type,
            "source_system": source_sys,
            "last_seen": last_seen_str,
        },
        "env": {
            "value": record["env"] or "non-production",
            "source_system": source_sys,
            "last_seen": last_seen_str,
        },
        "tier": {
            "value": record["tier"] or "Standard",
            "source_system": source_sys,
            "last_seen": last_seen_str,
        },
        "confidence": {
            "value": float(record["confidence"] or 1.0),
            "source_system": source_sys,
            "last_seen": last_seen_str,
        },
        "is_stale": {
            "value": bool(record["stale"] or False),
            "source_system": source_sys,
            "last_seen": last_seen_str,
        },
        "business_service": {
            "name": record["service_name"] or "Unassigned Service",
            "tier": record["service_tier"] or "Tier-2",
            "source_system": "itsm" if record["service_name"] else source_sys,
            "last_seen": last_seen_str,
        },
        "owner": {
            "group": record["owner_group"] or "CloudOps",
            "source_system": "itsm" if record["owner_group"] else source_sys,
            "last_seen": last_seen_str,
        },
    }
