"""Unit tests for Azure connector extraction and normalization."""

from datetime import datetime, timezone
import pytest
from connectors.azure.extract import (
    build_nic_index,
    map_vm_to_normalised_record,
)


@pytest.fixture
def sample_nic_rows():
    return [
        {
            "id": "/subscriptions/d78af5f4-5d2d-4141-a725-2088437da0ca/resourceGroups/asmrg/providers/Microsoft.Network/networkInterfaces/mypcpoc237_z1",
            "name": "mypcpoc237_z1",
            "macAddress": "00-22-48-6E-2E-85",
            "ipConfigurations": [
                {
                    "name": "ipconfig1",
                    "properties": {
                        "primary": True,
                        "privateIPAddress": "10.0.0.4",
                        "subnet": {
                            "id": "/subscriptions/d78af5f4-5d2d-4141-a725-2088437da0ca/resourceGroups/asmrg/providers/Microsoft.Network/virtualNetworks/mypcpoc-vnet/subnets/default"
                        },
                    },
                }
            ],
        }
    ]


@pytest.fixture
def sample_vm_row():
    return {
        "id": "/subscriptions/d78af5f4-5d2d-4141-a725-2088437da0ca/resourceGroups/asmrg/providers/Microsoft.Compute/virtualMachines/mypcpoc",
        "name": "mypcpoc",
        "resourceGroup": "asmrg",
        "location": "centralindia",
        "vmId": "46e8ff7b-80fb-493d-a3c4-613feafb4177",
        "vmSize": "Standard_D4s_v3",
        "computerName": "mypcpoc",
        "osType": "Windows",
        "osDiskName": "mypcpoc_OsDisk_1",
        "osDiskId": "/subscriptions/d78af5f4-5d2d-4141-a725-2088437da0ca/resourceGroups/asmrg/providers/Microsoft.Compute/disks/mypcpoc_OsDisk_1",
        "tags": {"Environment": "NonProd", "Application": "ContextGraph"},
        "timeCreated": "2025-01-09T21:42:08.141Z",
        "networkInterfaces": [
            {
                "id": "/subscriptions/d78af5f4-5d2d-4141-a725-2088437da0ca/resourceGroups/asmrg/providers/Microsoft.Network/networkInterfaces/mypcpoc237_z1"
            }
        ],
    }


def test_build_nic_index(sample_nic_rows):
    index = build_nic_index(sample_nic_rows)
    nic_key = sample_nic_rows[0]["id"].lower()

    assert nic_key in index
    assert index[nic_key]["primary_ip"] == "10.0.0.4"
    assert index[nic_key]["mac_address"] == "00-22-48-6E-2E-85"
    assert "10.0.0.4" in index[nic_key]["all_ips"]
    assert len(index[nic_key]["subnets"]) == 1


def test_map_vm_to_normalised_record(sample_vm_row, sample_nic_rows):
    nic_index = build_nic_index(sample_nic_rows)
    observed = datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)

    record, raw_payload = map_vm_to_normalised_record(
        vm=sample_vm_row,
        nic_index=nic_index,
        tenant_id="t1",
        observed_at=observed,
    )

    assert record.tenant_id == "t1"
    assert record.source_system == "azure"
    assert record.source_id == sample_vm_row["id"]
    assert record.kind == "VM"
    assert record.name == "mypcpoc"
    assert record.fqdn == "mypcpoc"
    assert record.ip == "10.0.0.4"
    assert record.mac == "00-22-48-6E-2E-85"
    assert record.cloud_id == "46e8ff7b-80fb-493d-a3c4-613feafb4177"
    assert record.attributes["resource_group"] == "asmrg"
    assert record.attributes["location"] == "centralindia"
    assert record.attributes["vm_size"] == "Standard_D4s_v3"
    assert record.attributes["os_type"] == "Windows"
    assert record.attributes["tags"] == {"Environment": "NonProd", "Application": "ContextGraph"}

    # Relations check
    relation_types = [r.type for r in record.relations]
    assert "CONNECTS_TO" in relation_types
    assert "IN_SUBNET" in relation_types
    assert "DEPENDS_ON" in relation_types

    # Raw payload check
    assert "vm" in raw_payload
    assert "attached_nics" in raw_payload
    assert len(raw_payload["attached_nics"]) == 1


def test_map_vm_without_nics():
    vm_no_nics = {
        "id": "/subscriptions/d78af5f4-5d2d-4141-a725-2088437da0ca/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/lonely-vm",
        "name": "lonely-vm",
        "vmId": "11111111-2222-3333-4444-555555555555",
        "networkInterfaces": [],
    }
    record, raw = map_vm_to_normalised_record(vm_no_nics, nic_index={}, tenant_id="t1")
    assert record.name == "lonely-vm"
    assert record.ip is None
    assert record.mac is None
    assert len(record.relations) == 0
