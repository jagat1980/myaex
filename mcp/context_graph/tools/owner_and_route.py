"""Tool: owner_and_route

Resolves operational ownership, assignment groups, escalation contacts,
and permitted automation execution engines (e.g. BigFix) for a given Configuration Item.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

CYPHER_OWNER_AND_ROUTE = """
MATCH (c:CI)
WHERE (c.uid = $uid OR c.name = $ci) AND c.tenant_id = $tenant_id
OPTIONAL MATCH (c)-[:OWNED_BY]->(g:AssignmentGroup)
OPTIONAL MATCH (c)-[:SUPPORTS]->(s:BusinessService)-[:OWNED_BY]->(sg:AssignmentGroup)
RETURN c.name AS name,
       c.tier AS ci_tier,
       coalesce(g.name, sg.name, 'CloudOps-Windows') AS assignment_group,
       coalesce(g.escalation_channel, sg.escalation_channel, 'pagerduty://cloudops-oncall') AS escalation_channel,
       coalesce(c.permitted_executor, 'BigFix') AS permitted_executor,
       c.source_system AS source_system,
       c.last_seen AS last_seen
LIMIT 1
"""


async def execute_owner_and_route(
    driver: AsyncDriver,
    tenant_id: str,
    ci: str,
) -> Dict[str, Any]:
    """Execute parameterized owner and routing read transaction."""
    uid = f"{tenant_id}:{ci}" if ":" not in ci else ci

    async with driver.session() as session:
        result = await session.execute_read(
            _read_owner_and_route,
            tenant_id=tenant_id,
            ci=ci,
            uid=uid,
        )
        return result


async def _read_owner_and_route(
    tx: Any,
    tenant_id: str,
    ci: str,
    uid: str,
) -> Dict[str, Any]:
    cursor = await tx.run(CYPHER_OWNER_AND_ROUTE, tenant_id=tenant_id, ci=ci, uid=uid)
    record = await cursor.single()

    if not record:
        return {
            "root_ci": ci,
            "assignment_group": "CloudOps-Windows",
            "escalation_channel": "pagerduty://cloudops-oncall",
            "permitted_executor": "BigFix",
            "auto_remediation_permitted": True,
            "source_system": "default-policy",
            "last_seen": datetime.now(timezone.utc).isoformat(),
            "message": f"CI '{ci}' not found in CMDB; defaulted to standard CloudOps-Windows routing.",
        }

    last_seen_str = str(record["last_seen"]) if record["last_seen"] else datetime.now(timezone.utc).isoformat()
    source_sys = record["source_system"] or "itsm"

    return {
        "root_ci": ci,
        "ci_name": record["name"],
        "assignment_group": record["assignment_group"],
        "escalation_channel": record["escalation_channel"],
        "permitted_executor": record["permitted_executor"],
        "auto_remediation_permitted": record["permitted_executor"].lower() in ("bigfix", "azure-automation"),
        "source_system": source_sys,
        "last_seen": last_seen_str,
    }
