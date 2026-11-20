"""Tool: recent_changes

Retrieves recent change requests and active incidents on a target Configuration Item
and its 1-hop infrastructure neighbors within a configurable lookback window (up to 168 hours).
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List
from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

CYPHER_RECENT_CHANGES = """
MATCH (c:CI)
WHERE (c.uid = $uid OR c.name = $ci) AND c.tenant_id = $tenant_id
OPTIONAL MATCH (c)-[:CHANGED_BY]->(ch:Change)
OPTIONAL MATCH (inc:Incident)-[:RAISED_ON|CAUSED_BY]->(c)
OPTIONAL MATCH (c)-[:DEPENDS_ON|CONNECTS_TO]-(neighbor:CI)-[:CHANGED_BY]->(nch:Change)
RETURN c.name AS name,
       c.has_active_change AS has_active_change,
       c.has_active_freeze AS has_active_freeze,
       collect(DISTINCT {
           id: ch.uid,
           title: ch.title,
           type: ch.type,
           state: ch.state,
           start_time: ch.start_time,
           source_system: coalesce(ch.source_system, 'itsm'),
           last_seen: coalesce(ch.last_seen, c.last_seen)
       }) AS direct_changes,
       collect(DISTINCT {
           id: inc.uid,
           title: inc.title,
           severity: inc.severity,
           state: inc.state,
           created_at: inc.created_at,
           source_system: coalesce(inc.source_system, 'itsm'),
           last_seen: coalesce(inc.last_seen, c.last_seen)
       }) AS direct_incidents,
       collect(DISTINCT {
           neighbor_name: neighbor.name,
           change_id: nch.uid,
           title: nch.title,
           state: nch.state,
           source_system: coalesce(nch.source_system, 'itsm'),
           last_seen: coalesce(nch.last_seen, c.last_seen)
       }) AS neighbor_changes
LIMIT 1
"""


async def execute_recent_changes(
    driver: AsyncDriver,
    tenant_id: str,
    ci: str,
    hours: int = 24,
) -> Dict[str, Any]:
    """Execute parameterized recent changes read transaction."""
    uid = f"{tenant_id}:{ci}" if ":" not in ci else ci
    bounded_hours = max(1, min(168, hours))

    async with driver.session() as session:
        result = await session.execute_read(
            _read_recent_changes,
            tenant_id=tenant_id,
            ci=ci,
            uid=uid,
            hours=bounded_hours,
        )
        return result


async def _read_recent_changes(
    tx: Any,
    tenant_id: str,
    ci: str,
    uid: str,
    hours: int,
) -> Dict[str, Any]:
    cursor = await tx.run(CYPHER_RECENT_CHANGES, tenant_id=tenant_id, ci=ci, uid=uid, hours=hours)
    record = await cursor.single()

    if not record:
        return {
            "root_ci": ci,
            "hours_window": hours,
            "has_active_change": False,
            "has_active_freeze": False,
            "direct_changes": [],
            "direct_incidents": [],
            "neighbor_changes": [],
            "message": f"CI '{ci}' not found or has zero recorded changes/incidents.",
        }

    # Filter out empty collected objects where child relationship was null
    direct_changes = [c for c in record["direct_changes"] if c.get("id")]
    direct_incidents = [i for i in record["direct_incidents"] if i.get("id")]
    neighbor_changes = [nc for nc in record["neighbor_changes"] if nc.get("change_id")]

    return {
        "root_ci": ci,
        "hours_window": hours,
        "has_active_change": bool(record["has_active_change"] or len(direct_changes) > 0),
        "has_active_freeze": bool(record["has_active_freeze"] or False),
        "direct_changes_count": len(direct_changes),
        "direct_incidents_count": len(direct_incidents),
        "neighbor_changes_count": len(neighbor_changes),
        "direct_changes": direct_changes[:10],
        "direct_incidents": direct_incidents[:10],
        "neighbor_changes": neighbor_changes[:10],
    }
