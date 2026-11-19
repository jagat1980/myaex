"""Azure Resource Graph extraction and normalization logic."""

from datetime import datetime, timezone
from typing import Any
from connectors.common.models import NormalisedRecord, NormalisedRelation

VM_QUERY = """
Resources
| where type =~ 'microsoft.compute/virtualmachines'
| project id, name, resourceGroup, location, tags,
          vmId = tostring(properties.vmId),
          vmSize = tostring(properties.hardwareProfile.vmSize),
          computerName = tostring(properties.osProfile.computerName),
          osType = tostring(properties.storageProfile.osDisk.osType),
          osDiskName = tostring(properties.storageProfile.osDisk.name),
          osDiskId = tostring(properties.storageProfile.osDisk.managedDisk.id),
          networkInterfaces = properties.networkProfile.networkInterfaces,
          timeCreated = tostring(properties.timeCreated),
          properties
"""

NIC_QUERY = """
Resources
| where type =~ 'microsoft.network/networkinterfaces'
| project id, name, resourceGroup, location,
          macAddress = tostring(properties.macAddress),
          ipConfigurations = properties.ipConfigurations,
          vmId = tostring(properties.virtualMachine.id),
          properties
"""


def build_nic_index(nic_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build a lookup map of NIC attributes indexed by lowercase resource ID."""
    index: dict[str, dict[str, Any]] = {}
    for nic in nic_rows:
        nic_id = str(nic.get("id", "")).lower()
        if not nic_id:
            continue

        ip_configs = (
            nic.get("ipConfigurations")
            or nic.get("properties_ipConfigurations")
            or (nic.get("properties", {}).get("ipConfigurations") if isinstance(nic.get("properties"), dict) else None)
            or []
        )
        mac_address = (
            nic.get("macAddress")
            or nic.get("properties_macAddress")
            or (nic.get("properties", {}).get("macAddress") if isinstance(nic.get("properties"), dict) else None)
        )

        primary_ip: str | None = None
        all_ips: list[str] = []
        subnets: list[str] = []

        for ipc in ip_configs:
            props = ipc.get("properties") or ipc
            private_ip = props.get("privateIPAddress")
            if private_ip:
                all_ips.append(str(private_ip))
                if props.get("primary") is True or primary_ip is None:
                    primary_ip = str(private_ip)
            subnet_ref = props.get("subnet") or {}
            subnet_id = subnet_ref.get("id")
            if subnet_id:
                subnets.append(str(subnet_id))

        index[nic_id] = {
            "id": nic.get("id"),
            "name": nic.get("name"),
            "mac_address": mac_address,
            "primary_ip": primary_ip,
            "all_ips": all_ips,
            "subnets": subnets,
            "raw": nic,
        }
    return index


def map_vm_to_normalised_record(
    vm: dict[str, Any],
    nic_index: dict[str, dict[str, Any]],
    tenant_id: str = "t1",
    observed_at: datetime | None = None,
) -> tuple[NormalisedRecord, dict[str, Any]]:
    """Map an Azure VM resource and attached NICs into a NormalisedRecord and raw payload."""
    if observed_at is None:
        observed_at = datetime.now(timezone.utc)
    elif observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)

    vm_id = str(vm.get("id", ""))
    vm_name = str(vm.get("name", ""))
    computer_name = vm.get("computerName") or vm_name
    cloud_id = vm.get("vmId") or vm_id

    # Correlate network interfaces
    nic_refs = (
        vm.get("networkInterfaces")
        or (vm.get("properties", {}).get("networkProfile", {}).get("networkInterfaces") if isinstance(vm.get("properties"), dict) else None)
        or []
    )
    attached_nics: list[dict[str, Any]] = []
    primary_ip: str | None = None
    primary_mac: str | None = None
    all_ips: list[str] = []
    all_macs: list[str] = []
    relations: list[NormalisedRelation] = []

    for ref in nic_refs:
        ref_id = str(ref.get("id", "")).lower()
        nic_entry = nic_index.get(ref_id)
        if nic_entry:
            attached_nics.append(nic_entry["raw"])
            if nic_entry["primary_ip"] and not primary_ip:
                primary_ip = nic_entry["primary_ip"]
            if nic_entry["mac_address"] and not primary_mac:
                primary_mac = nic_entry["mac_address"]
            all_ips.extend(nic_entry["all_ips"])
            if nic_entry["mac_address"]:
                all_macs.append(nic_entry["mac_address"])

            relations.append(
                NormalisedRelation(
                    type="CONNECTS_TO",
                    target_source_system="azure",
                    target_source_id=str(nic_entry["id"]),
                    target_kind="NIC",
                )
            )
            for subnet in nic_entry["subnets"]:
                relations.append(
                    NormalisedRelation(
                        type="IN_SUBNET",
                        target_source_system="azure",
                        target_source_id=subnet,
                        target_kind="Subnet",
                    )
                )

    os_disk_id = vm.get("osDiskId")
    if os_disk_id:
        relations.append(
            NormalisedRelation(
                type="DEPENDS_ON",
                target_source_system="azure",
                target_source_id=str(os_disk_id),
                target_kind="Disk",
            )
        )

    fqdn = computer_name.lower() if computer_name else None

    attributes: dict[str, Any] = {
        "resource_group": vm.get("resourceGroup"),
        "location": vm.get("location"),
        "vm_size": vm.get("vmSize"),
        "os_type": vm.get("osType") or "Windows",
        "tags": vm.get("tags") or {},
        "all_ips": sorted(list(set(all_ips))),
        "all_macs": sorted(list(set(all_macs))),
        "time_created": vm.get("timeCreated"),
    }

    record = NormalisedRecord(
        tenant_id=tenant_id,
        source_system="azure",
        source_id=vm_id,
        kind="VM",
        name=vm_name,
        fqdn=fqdn,
        ip=primary_ip,
        mac=primary_mac,
        cloud_id=str(cloud_id),
        attributes=attributes,
        relations=relations,
        observed_at=observed_at,
    )

    raw_payload = {
        "vm": vm,
        "attached_nics": attached_nics,
    }

    return record, raw_payload
