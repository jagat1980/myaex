"""Tool: blast_radius

Evaluates the downstream blast radius up to 3 graph hops for a given Configuration Item.
Enforces Hard Safety Rule 5 (Fixed parameterized Cypher, read transactions only, LIMIT 200).
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List
from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

CYPHER_BLAST_RADIUS = """
MATCH (c:CI)
WHERE (c.uid = $uid OR c.name = $ci) AND c.tenant_id = $tenant_id
MATCH path = (c)-[r:DEPENDS_ON|CONNECTS_TO|SUPPORTS*1..3]->(target:CI)
WHERE length(path) <= $hops AND target.tenant_id = $tenant_id
OPTIONAL MATCH (target)-[:SUPPORTS]->(s:BusinessService)
RETURN target.uid AS uid,
       target.name AS name,
       labels(target) AS labels,
       target.type AS type,
       target.tier AS tier,
       target.source_system AS source_system,
       target.last_seen AS last_seen,
       length(path) AS distance,
       collect(DISTINCT s.name) AS services
LIMIT 200
"""


async def execute_blast_radius(
    driver: AsyncDriver,
    tenant_id: str,
    ci: str,
    hops: int = 2,
) -> Dict[str, Any]:
    """Execute parameterized blast radius graph traversal."""
    uid = f"{tenant_id}:{ci}" if ":" not in ci else ci
    bounded_hops = max(1, min(3, hops))

    async with driver.session() as session:
        result = await session.execute_read(
            _read_blast_radius,
            tenant_id=tenant_id,
            ci=ci,
            uid=uid,
            hops=bounded_hops,
        )
        return result


async def _read_blast_radius(
    tx: Any,
    tenant_id: str,
    ci: str,
    uid: str,
    hops: int,
) -> Dict[str, Any]:
    cursor = await tx.run(CYPHER_BLAST_RADIUS, tenant_id=tenant_id, ci=ci, uid=uid, hops=hops)
    records = await cursor.data()

    downstream_cis: List[Dict[str, Any]] = []
    affected_services: set[str] = set()

    for r in records:
        last_seen_str = str(r["last_seen"]) if r["last_seen"] else datetime.now(timezone.utc).isoformat()
        ci_type = r["type"] or ([lbl for lbl in r["labels"] if lbl != "CI"] or ["CI"])[0]
        
        downstream_cis.append({
            "ci_id": r["uid"],
            "name": r["name"],
            "type": ci_type,
            "tier": r["tier"] or "Standard",
            "distance_hops": r["distance"],
            "source_system": r["source_system"] or "topology",
            "last_seen": last_seen_str,
        })
        for s in r["services"]:
            if s:
                affected_services.add(s)

    return {
        "root_ci": ci,
        "hops_evaluated": hops,
        "downstream_ci_count": len(downstream_cis),
        "downstream_service_count": len(affected_services),
        "affected_services": sorted(list(affected_services)),
        "downstream_cis": downstream_cis[:50],  # Bound payload to keep tokens < 4k
        "is_blast_radius_safe": len(affected_services) <= 2 and len(downstream_cis) <= 10,
    }
