"""Unit tests for all 6 Context Graph MCP tools."""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List
import pytest
from pydantic import ValidationError

from context_graph.auth import tenant_context
from context_graph.models import (
    BackupStatusInput,
    BlastRadiusInput,
    GetCIContextInput,
    OwnerAndRouteInput,
    RecentChangesInput,
    SimilarIncidentsInput,
)
from context_graph.server import (
    backup_status,
    blast_radius,
    get_ci_context,
    owner_and_route,
    recent_changes,
    set_db_pool,
    set_neo4j_driver,
    similar_incidents,
)
from context_graph.tests.conftest import (
    MockAsyncpgPool,
    MockDriver,
    MockTransaction,
)


@pytest.fixture(autouse=True)
def set_tenant() -> Any:
    """Set default test tenant for all tool tests."""
    token = tenant_context.set("t1")
    yield
    tenant_context.reset(token)


@pytest.mark.asyncio
async def test_get_ci_context_found(fixture_ci_record: Dict[str, Any]) -> None:
    driver = MockDriver(MockTransaction(single_record=fixture_ci_record))
    set_neo4j_driver(driver)

    result = await get_ci_context(ci="mypcpoc")
    assert result["found"] is True
    assert result["ci_id"] == "t1:46e8ff7b-80fb-493d-a3c4-613feafb4177"
    assert result["name"] == "mypcpoc"
    assert result["type"]["value"] == "VM"
    assert result["type"]["source_system"] == "azure"
    assert result["env"]["value"] == "non-production"
    assert result["business_service"]["name"] == "POC-Portal"
    assert result["owner"]["group"] == "CloudOps-Windows"


@pytest.mark.asyncio
async def test_get_ci_context_not_found() -> None:
    driver = MockDriver(MockTransaction(single_record=None))
    set_neo4j_driver(driver)

    result = await get_ci_context(ci="nonexistent-vm")
    assert result["found"] is False
    assert "not found" in result["message"]


@pytest.mark.asyncio
async def test_blast_radius(fixture_blast_radius_records: List[Dict[str, Any]]) -> None:
    driver = MockDriver(MockTransaction(multi_records=fixture_blast_radius_records))
    set_neo4j_driver(driver)

    result = await blast_radius(ci="mypcpoc", hops=2)
    assert result["root_ci"] == "mypcpoc"
    assert result["hops_evaluated"] == 2
    assert result["downstream_ci_count"] == 2
    assert result["downstream_service_count"] == 1
    assert "POC-Portal" in result["affected_services"]
    assert result["is_blast_radius_safe"] is True
    assert len(result["downstream_cis"]) == 2


@pytest.mark.asyncio
async def test_recent_changes() -> None:
    recent_record = {
        "name": "mypcpoc",
        "has_active_change": True,
        "has_active_freeze": False,
        "direct_changes": [
            {
                "id": "CHG-001",
                "title": "Windows Security Patching Batch A",
                "type": "Standard",
                "state": "Implemented",
                "start_time": "2026-11-20T08:00:00Z",
                "source_system": "itsm",
                "last_seen": "2026-11-20T08:00:00Z",
            }
        ],
        "direct_incidents": [],
        "neighbor_changes": [],
    }
    driver = MockDriver(MockTransaction(single_record=recent_record))
    set_neo4j_driver(driver)

    result = await recent_changes(ci="mypcpoc", hours=48)
    assert result["root_ci"] == "mypcpoc"
    assert result["hours_window"] == 48
    assert result["has_active_change"] is True
    assert result["direct_changes_count"] == 1
    assert result["direct_changes"][0]["id"] == "CHG-001"


@pytest.mark.asyncio
async def test_backup_status_within_rpo() -> None:
    backup_record = {
        "name": "mypcpoc",
        "backup_age_hours": 3.5,
        "backup_healthy": True,
        "job_name": "Veeam-Windows-Daily",
        "last_success": "2026-11-20T06:30:00Z",
        "restore_point_time": "2026-11-20T06:30:00Z",
        "source_system": "veeam",
        "last_seen": "2026-11-20T06:30:00Z",
    }
    driver = MockDriver(MockTransaction(single_record=backup_record))
    set_neo4j_driver(driver)

    result = await backup_status(ci="mypcpoc")
    assert result["root_ci"] == "mypcpoc"
    assert result["backup_found"] is True
    assert result["backup_healthy"] is True
    assert result["within_rpo"] is True
    assert result["restore_point_age_hours"] == 3.5
    assert result["last_backup_job"] == "Veeam-Windows-Daily"


@pytest.mark.asyncio
async def test_similar_incidents(fixture_vector_rows: List[Dict[str, Any]]) -> None:
    pool = MockAsyncpgPool(fixture_vector_rows)
    set_db_pool(pool)

    result = await similar_incidents(text="disk space full cbs log cleanup", ci="mypcpoc", k=2)
    assert result["query"] == "disk space full cbs log cleanup"
    assert result["ci_context"] == "mypcpoc"
    assert result["results_count"] == 2
    assert result["results"][0]["doc_id"] == "INC-1001"
    assert result["results"][0]["similarity"] == 0.8950
    assert result["results"][1]["doc_id"] == "RB-3001"


@pytest.mark.asyncio
async def test_owner_and_route() -> None:
    owner_record = {
        "name": "mypcpoc",
        "ci_tier": "Tier-2",
        "assignment_group": "CloudOps-Windows",
        "escalation_channel": "pagerduty://cloudops-oncall",
        "permitted_executor": "BigFix",
        "source_system": "itsm",
        "last_seen": "2026-11-20T10:00:00Z",
    }
    driver = MockDriver(MockTransaction(single_record=owner_record))
    set_neo4j_driver(driver)

    result = await owner_and_route(ci="mypcpoc")
    assert result["root_ci"] == "mypcpoc"
    assert result["assignment_group"] == "CloudOps-Windows"
    assert result["escalation_channel"] == "pagerduty://cloudops-oncall"
    assert result["permitted_executor"] == "BigFix"
    assert result["auto_remediation_permitted"] is True


def test_input_validation_boundaries() -> None:
    """Validate Pydantic models reject invalid inputs."""
    # Invalid characters in CI
    with pytest.raises(ValidationError):
        GetCIContextInput(ci="mypc; rm -rf /")

    # Blast radius hops out of bounds (> 3)
    with pytest.raises(ValidationError):
        BlastRadiusInput(ci="mypcpoc", hops=5)

    # Recent changes hours out of bounds (> 168)
    with pytest.raises(ValidationError):
        RecentChangesInput(ci="mypcpoc", hours=500)

    # Similar incidents text too short (< 3)
    with pytest.raises(ValidationError):
        SimilarIncidentsInput(text="ab", k=3)

    # Similar incidents k out of bounds (> 5)
    with pytest.raises(ValidationError):
        SimilarIncidentsInput(text="valid query", k=10)
