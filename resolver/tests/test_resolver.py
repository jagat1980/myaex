"""Unit tests for the Entity Resolver and 5-tier identity matching."""

from datetime import datetime, timezone
import uuid
import pytest
from connectors.common.models import NormalisedRecord
from resolver.matcher import EntityMatcher
from resolver.models import MatchConfidence, MatchKeyType


@pytest.fixture
def matcher():
    return EntityMatcher()


@pytest.fixture
def base_azure_vm():
    return NormalisedRecord(
        tenant_id="t1",
        source_system="azure",
        source_id="/subscriptions/d78af5f4-5d2d-4141-a725-2088437da0ca/resourceGroups/asmrg/providers/Microsoft.Compute/virtualMachines/mypcpoc",
        kind="VM",
        name="mypcpoc",
        fqdn="mypcpoc.corp.local",
        ip="10.0.0.4",
        mac="00-22-48-6E-2E-85",
        cloud_id="46e8ff7b-80fb-493d-a3c4-613feafb4177",
        attributes={"resource_group": "asmrg", "vm_size": "Standard_D4s_v3"},
        observed_at=datetime.now(timezone.utc),
    )


def test_tier1_cloud_id_match(matcher, base_azure_vm):
    # Known CI in memory established by Azure
    canonical_id = uuid.UUID(base_azure_vm.cloud_id)
    known_cis = {
        canonical_id: {
            "name": "mypcpoc",
            "cloud_id": base_azure_vm.cloud_id,
            "ip": "10.0.0.4",
        }
    }
    existing_aliases = {}

    # Incoming record from another source referencing the same cloud_id
    incoming = NormalisedRecord(
        tenant_id="t1",
        source_system="solarwinds",
        source_id="swo:host:123",
        kind="VM",
        name="mypcpoc-swo",
        cloud_id=base_azure_vm.cloud_id,
        observed_at=datetime.now(timezone.utc),
    )

    res = matcher.match(incoming, existing_aliases, known_cis)
    assert res.ci_id == canonical_id
    assert res.confidence == MatchConfidence.CLOUD_ID
    assert res.matched_key_type == MatchKeyType.CLOUD_ID
    assert not res.is_conflict


def test_tier3_fqdn_match(matcher):
    canonical_id = uuid.uuid4()
    known_cis = {
        canonical_id: {
            "name": "server01",
            "fqdn": "server01.corp.internal",
            "ip": "10.1.2.3",
        }
    }
    existing_aliases = {}

    incoming = NormalisedRecord(
        tenant_id="t1",
        source_system="solarwinds",
        source_id="e-999",
        kind="Host",
        name="server01",
        fqdn="SERVER01.CORP.INTERNAL",  # case-insensitive check
        observed_at=datetime.now(timezone.utc),
    )

    res = matcher.match(incoming, existing_aliases, known_cis)
    assert res.ci_id == canonical_id
    assert res.confidence == MatchConfidence.FQDN
    assert res.matched_key_type == MatchKeyType.FQDN
    assert not res.is_conflict


def test_tier4_hostname_ip_match(matcher):
    canonical_id = uuid.uuid4()
    known_cis = {
        canonical_id: {
            "name": "db-prod",
            "ip": "10.240.1.100",
            "all_ips": ["10.240.1.100"],
        }
    }
    existing_aliases = {}

    incoming = NormalisedRecord(
        tenant_id="t1",
        source_system="solarwinds",
        source_id="e-888",
        kind="Host",
        name="db-prod",
        ip="10.240.1.100",
        observed_at=datetime.now(timezone.utc),
    )

    res = matcher.match(incoming, existing_aliases, known_cis)
    assert res.ci_id == canonical_id
    assert res.confidence == MatchConfidence.HOSTNAME_IP
    assert res.matched_key_type == MatchKeyType.HOSTNAME_IP
    assert not res.is_conflict


def test_tier5_hostname_conflict_detection(matcher):
    canonical_id = uuid.uuid4()
    known_cis = {
        canonical_id: {
            "name": "webserver",
            "ip": "10.0.1.50",
        }
    }
    existing_aliases = {}

    # Incoming record has SAME hostname but CONFLICTING IP address
    incoming_conflict = NormalisedRecord(
        tenant_id="t1",
        source_system="solarwinds",
        source_id="e-777",
        kind="Host",
        name="webserver",
        ip="192.168.10.50",  # Different subnet/IP -> Conflict!
        observed_at=datetime.now(timezone.utc),
    )

    res = matcher.match(incoming_conflict, existing_aliases, known_cis)
    assert res.is_conflict is True
    assert res.ci_id != canonical_id  # Must NOT merge!
    assert "conflicting IP addresses" in str(res.conflict_reason)


def test_new_entity_generation(matcher, base_azure_vm):
    # Empty known CIs
    res = matcher.match(base_azure_vm, existing_aliases={}, known_cis={})
    assert res.is_new is True
    assert res.confidence == 1.00  # Authoritative Azure
    assert res.ci_id == uuid.UUID(base_azure_vm.cloud_id)
