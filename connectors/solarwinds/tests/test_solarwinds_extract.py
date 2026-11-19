"""Unit tests for SolarWinds SaaS connector extraction and safety rules."""

from datetime import datetime, timezone
import pytest
import httpx
from connectors.solarwinds.extract import extract_solarwinds_host
from connectors.solarwinds.client import SolarWindsSaaSClient, SolarWindsReadOnlyTransport


@pytest.fixture
def sample_swo_host_entity():
    return {
        "id": "swo:entity:host:e-0123456789abcdef",
        "name": "mypcpoc",
        "displayName": "mypcpoc.corp.local",
        "properties": {
            "host.name": "mypcpoc",
            "host.fqdn": "mypcpoc.corp.local",
            "host.ip": "10.0.0.4",
            "host.mac": "00-22-48-6E-2E-85",
            "host.os.type": "windows",
            "host.os.version": "Windows Server 2019",
            "host.cpu.count": 4,
            "host.memory.bytes": 17179869184,
            "cloud.provider": "azure",
            "cloud.resource.id": "/subscriptions/d78af5f4-5d2d-4141-a725-2088437da0ca/resourceGroups/asmrg/providers/Microsoft.Compute/virtualMachines/mypcpoc",
            "status": "UP",
        },
        "tags": {
            "Environment": "NonProd",
            "Application": "ContextGraph",
        },
        "relations": [
            {
                "type": "CONNECTS_TO",
                "target": "swo:entity:interface:int-1",
                "target_kind": "NIC",
            }
        ],
    }


def test_extract_solarwinds_host(sample_swo_host_entity):
    observed = datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)
    record, raw_payload = extract_solarwinds_host(
        entity=sample_swo_host_entity,
        tenant_id="t1",
        observed_at=observed,
    )

    assert record.tenant_id == "t1"
    assert record.source_system == "solarwinds"
    assert record.source_id == "swo:entity:host:e-0123456789abcdef"
    assert record.kind == "VM"  # Because cloud.provider is azure
    assert record.name == "mypcpoc"
    assert record.fqdn == "mypcpoc.corp.local"
    assert record.ip == "10.0.0.4"
    assert record.mac == "00-22-48-6E-2E-85"
    assert record.cloud_id == "/subscriptions/d78af5f4-5d2d-4141-a725-2088437da0ca/resourceGroups/asmrg/providers/Microsoft.Compute/virtualMachines/mypcpoc"
    assert record.attributes["status"] == "UP"
    assert record.attributes["os_type"] == "windows"
    assert record.attributes["cpu_count"] == 4
    assert record.attributes["tags"] == {"Environment": "NonProd", "Application": "ContextGraph"}

    assert len(record.relations) == 1
    assert record.relations[0].type == "CONNECTS_TO"
    assert record.relations[0].target_source_id == "swo:entity:interface:int-1"
    assert record.relations[0].target_kind == "NIC"

    assert raw_payload == sample_swo_host_entity


def test_extract_solarwinds_onprem_host():
    onprem_entity = {
        "id": "swo:entity:host:e-9999",
        "displayName": "db-server-01",
        "attributes": {
            "hostname": "db-server-01.local",
            "ipAddresses": ["192.168.1.50"],
            "macAddress": "00:11:22:33:44:55",
            "status": "HEALTHY",
        },
    }
    record, _ = extract_solarwinds_host(onprem_entity, tenant_id="t1")
    assert record.name == "db-server-01"
    assert record.kind == "Host"  # No cloud provider -> Host
    assert record.ip == "192.168.1.50"
    assert record.mac == "00:11:22:33:44:55"
    assert record.cloud_id is None


@pytest.mark.asyncio
async def test_read_only_transport_safety_assertion():
    """Hard Safety Rule 3: Assert that non-GET methods fail immediately."""
    transport = SolarWindsReadOnlyTransport()
    post_request = httpx.Request("POST", "https://api.eu-01.cloud.solarwinds.com/v1/entities")

    with pytest.raises(AssertionError) as exc_info:
        await transport.handle_async_request(post_request)
    assert "Hard Safety Rule 3" in str(exc_info.value)
