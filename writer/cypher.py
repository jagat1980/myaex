"""Fixed, parameterized Cypher templates for the temporal graph writer.

Hard Safety Rule 5: Zero dynamic/LLM-generated Cypher. Only fixed parameterized queries.
Data Model Invariants:
- uid = "<tenant_id>:<ci_id>"
- Every infrastructure node has :CI plus subtype (:VM, :Host)
- Every node and edge carries: tenant_id, source_system, source_id, valid_from, valid_to, last_seen, confidence
- Never hard-delete history: close edges by setting valid_to.
"""

UPSERT_NODES_BATCH = """
UNWIND $batch AS item
MERGE (c:CI {uid: item.uid})
ON CREATE SET
  c.tenant_id = item.tenant_id,
  c.ci_id = item.ci_id,
  c.name = item.name,
  c.fqdn = item.fqdn,
  c.ip = item.ip,
  c.mac = item.mac,
  c.cloud_id = item.cloud_id,
  c.source_system = item.source_system,
  c.source_id = item.source_id,
  c.confidence = item.confidence,
  c.last_seen = datetime(item.last_seen),
  c.valid_from = datetime(item.observed_at),
  c.valid_to = null,
  c.stale = false
ON MATCH SET
  c.name = coalesce(item.name, c.name),
  c.fqdn = coalesce(item.fqdn, c.fqdn),
  c.ip = coalesce(item.ip, c.ip),
  c.mac = coalesce(item.mac, c.mac),
  c.cloud_id = coalesce(item.cloud_id, c.cloud_id),
  c.confidence = CASE WHEN item.confidence > c.confidence THEN item.confidence ELSE c.confidence END,
  c.last_seen = datetime(item.last_seen),
  c.stale = false
SET c += item.attributes
"""

SET_VM_LABELS = """
UNWIND $uids AS uid
MATCH (c:CI {uid: uid})
SET c:VM
"""

SET_HOST_LABELS = """
UNWIND $uids AS uid
MATCH (c:CI {uid: uid})
SET c:Host
"""

UPSERT_RELATIONS_CONNECTS_TO = """
UNWIND $rel_batch AS rel
MATCH (source:CI {uid: rel.source_uid})
MERGE (target:CI {uid: rel.target_uid})
ON CREATE SET
  target.tenant_id = rel.tenant_id,
  target.ci_id = rel.target_ci_id,
  target.name = rel.target_name,
  target.source_system = rel.source_system,
  target.source_id = rel.target_source_id,
  target.last_seen = datetime(rel.last_seen),
  target.valid_from = datetime(rel.observed_at),
  target.valid_to = null,
  target.stale = false
MERGE (source)-[r:CONNECTS_TO]->(target)
ON CREATE SET
  r.valid_from = datetime(rel.observed_at),
  r.valid_to = null,
  r.last_seen = datetime(rel.last_seen),
  r.source_system = rel.source_system,
  r.confidence = rel.confidence
ON MATCH SET
  r.last_seen = datetime(rel.last_seen),
  r.valid_to = null
SET r += rel.attributes
"""

UPSERT_RELATIONS_DEPENDS_ON = """
UNWIND $rel_batch AS rel
MATCH (source:CI {uid: rel.source_uid})
MERGE (target:CI {uid: rel.target_uid})
ON CREATE SET
  target.tenant_id = rel.tenant_id,
  target.ci_id = rel.target_ci_id,
  target.name = rel.target_name,
  target.source_system = rel.source_system,
  target.source_id = rel.target_source_id,
  target.last_seen = datetime(rel.last_seen),
  target.valid_from = datetime(rel.observed_at),
  target.valid_to = null,
  target.stale = false
MERGE (source)-[r:DEPENDS_ON]->(target)
ON CREATE SET
  r.valid_from = datetime(rel.observed_at),
  r.valid_to = null,
  r.last_seen = datetime(rel.last_seen),
  r.source_system = rel.source_system,
  r.confidence = rel.confidence
ON MATCH SET
  r.last_seen = datetime(rel.last_seen),
  r.valid_to = null
SET r += rel.attributes
"""

CLOSE_STALE_EDGES = """
MATCH (source:CI {uid: $source_uid})-[r]->(target:CI)
WHERE r.source_system = $source_system
  AND r.last_seen < datetime($sync_started_at)
  AND r.valid_to IS NULL
SET r.valid_to = datetime($sync_started_at)
RETURN count(r) AS closed_count
"""

MARK_STALE_CIS = """
MATCH (c:CI {tenant_id: $tenant_id})
WHERE c.last_seen < datetime($stale_threshold) AND c.stale = false
SET c.stale = true
RETURN count(c) AS stale_count
"""

COUNT_NODES_AND_EDGES = """
MATCH (c:CI {tenant_id: $tenant_id})
OPTIONAL MATCH (c)-[r]->()
RETURN count(DISTINCT c) AS node_count, count(r) AS edge_count
"""
