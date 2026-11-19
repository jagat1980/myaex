"""Temporal Graph Writer executing idempotent batch writes into Neo4j Community Edition."""

from datetime import datetime, timezone
import logging
from typing import Any
import uuid
from neo4j import Driver, ManagedTransaction
from resolver.models import ResolvedEntity
from writer.cypher import (
    UPSERT_NODES_BATCH,
    SET_VM_LABELS,
    SET_HOST_LABELS,
    UPSERT_RELATIONS_CONNECTS_TO,
    UPSERT_RELATIONS_DEPENDS_ON,
    CLOSE_STALE_EDGES,
    COUNT_NODES_AND_EDGES,
)

logger = logging.getLogger("writer.graph_writer")


def clean_attributes(raw_attrs: dict[str, Any]) -> dict[str, Any]:
    """Ensure attributes are Neo4j-compatible primitives, lists, or strings."""
    cleaned: dict[str, Any] = {}
    for k, v in raw_attrs.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            cleaned[k] = v
        elif isinstance(v, (list, tuple)):
            # Neo4j allows homogeneous lists of primitives
            if all(isinstance(x, (str, int, float, bool)) for x in v):
                cleaned[k] = list(v)
            else:
                cleaned[k] = [str(x) for x in v]
        elif isinstance(v, dict):
            # Flatten or serialize nested dicts (like tags)
            for sub_k, sub_v in v.items():
                if isinstance(sub_v, (str, int, float, bool)):
                    cleaned[f"{k}_{sub_k}"] = sub_v
                else:
                    cleaned[f"{k}_{sub_k}"] = str(sub_v)
        else:
            cleaned[k] = str(v)
    return cleaned


class TemporalGraphWriter:
    """Manages idempotent batch ingestion and temporal edge closure in Neo4j."""

    def __init__(self, driver: Driver, batch_size: int = 500) -> None:
        self.driver = driver
        self.batch_size = batch_size

    def write_entities(
        self,
        entities: list[ResolvedEntity],
        sync_started_at: datetime | None = None,
    ) -> dict[str, int]:
        """Upsert a list of resolved entities into Neo4j within write transactions."""
        if sync_started_at is None:
            sync_started_at = datetime.now(timezone.utc)
        elif sync_started_at.tzinfo is None:
            sync_started_at = sync_started_at.replace(tzinfo=timezone.utc)

        sync_str = sync_started_at.isoformat()

        if not entities:
            logger.info("No entities to write to graph.")
            return {"nodes": 0, "edges": 0, "edges_closed": 0}

        # 1. Prepare node payloads
        node_batch: list[dict[str, Any]] = []
        vm_uids: list[str] = []
        host_uids: list[str] = []

        connects_to_batch: list[dict[str, Any]] = []
        depends_on_batch: list[dict[str, Any]] = []
        source_uids_to_check: set[tuple[str, str]] = set()

        for entity in entities:
            observed_str = entity.observed_at.isoformat()
            node_dict = {
                "uid": entity.uid,
                "tenant_id": entity.tenant_id,
                "ci_id": str(entity.ci_id),
                "name": entity.canonical_name,
                "fqdn": entity.fqdn,
                "ip": entity.ip,
                "mac": entity.mac,
                "cloud_id": entity.cloud_id,
                "source_system": entity.source_system,
                "source_id": entity.source_id,
                "confidence": entity.confidence,
                "last_seen": sync_str,
                "observed_at": observed_str,
                "attributes": clean_attributes(entity.attributes),
            }
            node_batch.append(node_dict)

            if entity.kind.upper() == "VM":
                vm_uids.append(entity.uid)
            else:
                host_uids.append(entity.uid)

            source_uids_to_check.add((entity.uid, entity.source_system))

            # Relations
            for rel in entity.relations:
                target_uid = f"{entity.tenant_id}:{rel.target_source_system}:{rel.target_source_id}"
                target_ci_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, target_uid))
                rel_dict = {
                    "source_uid": entity.uid,
                    "target_uid": target_uid,
                    "tenant_id": entity.tenant_id,
                    "target_ci_id": target_ci_id,
                    "target_name": rel.target_source_id.split("/")[-1],
                    "source_system": entity.source_system,
                    "target_source_id": rel.target_source_id,
                    "confidence": entity.confidence,
                    "last_seen": sync_str,
                    "observed_at": observed_str,
                    "attributes": clean_attributes(rel.attributes),
                }
                if rel.type == "DEPENDS_ON":
                    depends_on_batch.append(rel_dict)
                else:
                    connects_to_batch.append(rel_dict)

        # 2. Execute node batch upserts in chunks
        nodes_written = 0
        with self.driver.session() as session:
            for i in range(0, len(node_batch), self.batch_size):
                chunk = node_batch[i : i + self.batch_size]
                session.execute_write(lambda tx: tx.run(UPSERT_NODES_BATCH, batch=chunk))
                nodes_written += len(chunk)

            # Apply specific labels
            if vm_uids:
                session.execute_write(lambda tx: tx.run(SET_VM_LABELS, uids=vm_uids))
            if host_uids:
                session.execute_write(lambda tx: tx.run(SET_HOST_LABELS, uids=host_uids))

            # 3. Execute edge batch upserts
            edges_written = 0
            if connects_to_batch:
                for i in range(0, len(connects_to_batch), self.batch_size):
                    chunk = connects_to_batch[i : i + self.batch_size]
                    session.execute_write(lambda tx: tx.run(UPSERT_RELATIONS_CONNECTS_TO, rel_batch=chunk))
                    edges_written += len(chunk)

            if depends_on_batch:
                for i in range(0, len(depends_on_batch), self.batch_size):
                    chunk = depends_on_batch[i : i + self.batch_size]
                    session.execute_write(lambda tx: tx.run(UPSERT_RELATIONS_DEPENDS_ON, rel_batch=chunk))
                    edges_written += len(chunk)

            # 4. Temporal edge closure: Close edges that were not observed in this sync
            edges_closed = 0
            for src_uid, src_sys in source_uids_to_check:
                result = session.execute_write(
                    lambda tx: tx.run(
                        CLOSE_STALE_EDGES,
                        source_uid=src_uid,
                        source_system=src_sys,
                        sync_started_at=sync_str,
                    ).single()
                )
                if result and result["closed_count"]:
                    edges_closed += int(result["closed_count"])

        logger.info(
            "Graph sync complete: %d nodes, %d edges upserted, %d temporal edges closed",
            nodes_written,
            edges_written,
            edges_closed,
        )
        return {
            "nodes": nodes_written,
            "edges": edges_written,
            "edges_closed": edges_closed,
        }

    def get_graph_counts(self, tenant_id: str = "t1") -> dict[str, int]:
        """Query total node and edge counts for a tenant."""
        with self.driver.session() as session:
            record = session.execute_read(
                lambda tx: tx.run(COUNT_NODES_AND_EDGES, tenant_id=tenant_id).single()
            )
            if record:
                return {
                    "nodes": int(record["node_count"]),
                    "edges": int(record["edge_count"]),
                }
            return {"nodes": 0, "edges": 0}
