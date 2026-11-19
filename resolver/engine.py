"""Entity resolution orchestration engine."""

import json
import logging
from typing import Any
import uuid
import asyncpg
from connectors.azure.extract import build_nic_index, map_vm_to_normalised_record
from connectors.common.models import NormalisedRecord
from connectors.solarwinds.extract import extract_solarwinds_host
from resolver.matcher import EntityMatcher
from resolver.models import ResolutionResult, ResolvedEntity
from resolver.store import AliasStore

logger = logging.getLogger("resolver.engine")


class ResolutionEngine:
    """Coordinates parsing of raw records, identity matching, and alias persistence."""

    def __init__(self, conn: asyncpg.Connection, tenant_id: str = "t1") -> None:
        self.conn = conn
        self.tenant_id = tenant_id
        self.store = AliasStore(conn)
        self.matcher = EntityMatcher()

    def parse_raw_record(self, raw_row: dict[str, Any]) -> NormalisedRecord | None:
        """Parse raw payload from raw_records table into a NormalisedRecord."""
        source_system = str(raw_row["source_system"])
        payload = raw_row["payload"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                logger.error("Failed to parse JSON payload for %s:%s", source_system, raw_row["source_id"])
                return None

        observed_at = raw_row["observed_at"]

        if source_system == "azure":
            vm_data = payload.get("vm", payload)
            attached_nics = payload.get("attached_nics", [])
            nic_index = build_nic_index(attached_nics)
            record, _ = map_vm_to_normalised_record(
                vm=vm_data,
                nic_index=nic_index,
                tenant_id=self.tenant_id,
                observed_at=observed_at,
            )
            return record

        elif source_system == "solarwinds":
            record, _ = extract_solarwinds_host(
                entity=payload,
                tenant_id=self.tenant_id,
                observed_at=observed_at,
            )
            return record

        return None

    async def run(self) -> list[ResolvedEntity]:
        """Execute full resolution cycle across all latest raw records for the tenant."""
        existing_aliases = await self.store.load_existing_aliases(self.tenant_id)
        logger.info("Loaded %d existing CI aliases from ci_alias", len(existing_aliases))

        raw_rows = await self.store.fetch_latest_raw_records(self.tenant_id)
        logger.info("Fetched %d latest raw records from raw_records", len(raw_rows))

        # Prioritize authoritative sources (Azure) first to establish the baseline
        def sort_priority(r: dict[str, Any]) -> int:
            sys = str(r["source_system"]).lower()
            if sys == "azure":
                return 0
            elif sys == "itsm":
                return 1
            return 2

        sorted_rows = sorted(raw_rows, key=sort_priority)

        known_cis: dict[uuid.UUID, dict[str, Any]] = {}
        resolved_entities: list[ResolvedEntity] = []

        for row in sorted_rows:
            record = self.parse_raw_record(row)
            if not record:
                continue

            match_result: ResolutionResult = self.matcher.match(
                record=record,
                existing_aliases=existing_aliases,
                known_cis=known_cis,
            )

            ci_id = match_result.ci_id

            if match_result.is_conflict:
                await self.store.record_conflict(
                    tenant_id=self.tenant_id,
                    ci_id_candidate=ci_id,
                    source_system=record.source_system,
                    source_id=record.source_id,
                    conflict_reason=match_result.conflict_reason or "Unspecified ambiguity",
                    raw_payload=row["payload"] if isinstance(row["payload"], dict) else {"raw": row["payload"]},
                )
            else:
                alias_key = f"{record.source_system}:{record.source_id}"
                existing_aliases[alias_key] = ci_id

                await self.store.upsert_ci_alias(
                    tenant_id=self.tenant_id,
                    source_system=record.source_system,
                    source_id=record.source_id,
                    ci_id=ci_id,
                    confidence=match_result.confidence,
                )

                # Initialize or merge known CI properties
                if ci_id not in known_cis:
                    known_cis[ci_id] = {
                        "name": record.name,
                        "fqdn": record.fqdn,
                        "ip": record.ip,
                        "mac": record.mac,
                        "cloud_id": record.cloud_id,
                        "confidence": match_result.confidence,
                        "kind": record.kind,
                        "all_ips": record.attributes.get("all_ips", ([record.ip] if record.ip else [])),
                    }
                else:
                    existing = known_cis[ci_id]
                    # Update fields if empty or if authoritative Azure
                    if record.source_system == "azure":
                        existing["name"] = record.name
                        existing["fqdn"] = record.fqdn or existing.get("fqdn")
                        existing["ip"] = record.ip or existing.get("ip")
                        existing["mac"] = record.mac or existing.get("mac")
                        existing["cloud_id"] = record.cloud_id or existing.get("cloud_id")
                        existing["confidence"] = max(existing.get("confidence", 0.0), match_result.confidence)
                    else:
                        existing["fqdn"] = existing.get("fqdn") or record.fqdn
                        existing["ip"] = existing.get("ip") or record.ip
                        existing["mac"] = existing.get("mac") or record.mac

            # Build resolved entity
            canonical_props = known_cis.get(ci_id, {})
            resolved_entity = ResolvedEntity(
                tenant_id=self.tenant_id,
                ci_id=ci_id,
                uid=f"{self.tenant_id}:{ci_id}",
                kind=record.kind,
                canonical_name=canonical_props.get("name", record.name),
                source_system=record.source_system,
                source_id=record.source_id,
                confidence=match_result.confidence,
                fqdn=canonical_props.get("fqdn") or record.fqdn,
                ip=canonical_props.get("ip") or record.ip,
                mac=canonical_props.get("mac") or record.mac,
                cloud_id=canonical_props.get("cloud_id") or record.cloud_id,
                attributes=record.attributes,
                relations=record.relations,
                observed_at=record.observed_at,
            )
            resolved_entities.append(resolved_entity)

        logger.info(
            "Resolution completed: %d total entities resolved across %d distinct CIs",
            len(resolved_entities),
            len(known_cis),
        )
        return resolved_entities
