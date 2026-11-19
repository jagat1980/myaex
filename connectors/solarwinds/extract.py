"""SolarWinds Observability SaaS entity extraction and normalization logic."""

from datetime import datetime, timezone
from typing import Any
from connectors.common.models import NormalisedRecord, NormalisedRelation


def extract_solarwinds_host(
    entity: dict[str, Any],
    tenant_id: str = "t1",
    observed_at: datetime | None = None,
) -> tuple[NormalisedRecord, dict[str, Any]]:
    """Normalize a SolarWinds Observability SaaS host entity into a NormalisedRecord."""
    if observed_at is None:
        observed_at = datetime.now(timezone.utc)
    elif observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)

    entity_id = str(entity.get("id") or entity.get("entityId") or "")
    display_name = str(entity.get("name") or entity.get("displayName") or entity_id)

    props = entity.get("properties") or entity.get("attributes") or {}

    # Extract Hostname / FQDN
    fqdn = (
        props.get("host.fqdn")
        or props.get("fqdn")
        or props.get("hostname")
        or props.get("host.name")
        or entity.get("displayName")
    )
    if fqdn:
        fqdn = str(fqdn).lower()

    # Extract Primary IP
    ip = (
        props.get("host.ip")
        or props.get("ip")
        or props.get("privateIpAddress")
        or props.get("primary_ip")
    )
    if not ip:
        ip_list = props.get("ipAddresses") or props.get("ips") or []
        if isinstance(ip_list, list) and len(ip_list) > 0:
            ip = str(ip_list[0])

    # Extract Primary MAC
    mac = (
        props.get("host.mac")
        or props.get("mac")
        or props.get("macAddress")
    )

    # Cloud ID / Azure Resource ID correlation
    cloud_id = (
        props.get("cloud.resource.id")
        or props.get("azure.resource.id")
        or props.get("cloud_id")
        or props.get("cloud.instance.id")
    )

    # Determine kind: VM vs Host
    cloud_provider = str(props.get("cloud.provider", "")).lower()
    is_vm = (
        "azure" in cloud_provider
        or "aws" in cloud_provider
        or "gcp" in cloud_provider
        or props.get("hypervisor") is not None
        or props.get("vm") is True
    )
    kind = "VM" if is_vm else "Host"

    # Relations (interfaces, parent clusters, or monitors)
    relations: list[NormalisedRelation] = []
    raw_relations = entity.get("relations") or []
    for rel in raw_relations:
        rel_type = rel.get("type", "CONNECTS_TO")
        target_id = rel.get("target") or rel.get("id")
        if target_id:
            relations.append(
                NormalisedRelation(
                    type=rel_type,
                    target_source_system="solarwinds",
                    target_source_id=str(target_id),
                    target_kind=rel.get("target_kind", "CI"),
                )
            )

    attributes: dict[str, Any] = {
        "status": props.get("status") or entity.get("status", "UNKNOWN"),
        "os_type": props.get("host.os.type") or props.get("os_type"),
        "os_version": props.get("host.os.version") or props.get("os_version"),
        "cpu_count": props.get("host.cpu.count") or props.get("cpu_count"),
        "memory_bytes": props.get("host.memory.bytes") or props.get("memory_bytes"),
        "cloud_provider": cloud_provider or None,
        "tags": entity.get("tags") or {},
    }

    record = NormalisedRecord(
        tenant_id=tenant_id,
        source_system="solarwinds",
        source_id=entity_id,
        kind=kind,
        name=display_name,
        fqdn=fqdn,
        ip=str(ip) if ip else None,
        mac=str(mac) if mac else None,
        cloud_id=str(cloud_id) if cloud_id else None,
        attributes=attributes,
        relations=relations,
        observed_at=observed_at,
    )

    return record, entity
