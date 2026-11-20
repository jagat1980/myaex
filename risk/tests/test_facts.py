"""Exhaustive unit tests for deterministic risk evaluation and autonomy tier mapping.

Target: 100% test coverage for risk/facts.py.
"""

from unittest.mock import MagicMock
import pytest
from risk.facts import compute_ci_risk, evaluate_autonomy_tier
from risk.models import AutonomyTier, BlastRadius, RiskFacts


@pytest.fixture
def clean_facts():
    """Returns a baseline RiskFacts instance meeting all invariants for L2 autonomy."""
    return RiskFacts(
        ci_uid="t1:vm-clean-01",
        ci_name="vm-clean-01",
        tenant_id="t1",
        blast_radius=BlastRadius(
            downstream_ci_count=1,
            downstream_service_count=0,
            downstream_services=[],
            max_hops=3,
        ),
        is_tier1=False,
        has_active_change=False,
        has_active_freeze=False,
        restore_point_age_hours=4.0,
        backup_healthy=True,
        has_exploited_vuln=False,
        is_stale=False,
        confidence=1.0,
    )


# --- L2 Autonomy Tests ---

def test_l2_autonomy_all_invariants_satisfied(clean_facts):
    tier, reasons = evaluate_autonomy_tier(clean_facts)
    assert tier == AutonomyTier.L2
    assert "All safety invariants satisfied" in reasons[0]


# --- L0 Hard Block Tests ---

def test_l0_tier1_service_blocks_automation(clean_facts):
    clean_facts.is_tier1 = True
    tier, reasons = evaluate_autonomy_tier(clean_facts)
    assert tier == AutonomyTier.L0
    assert any("Tier 1 mission-critical" in r for r in reasons)


def test_l0_active_change_freeze_blocks_automation(clean_facts):
    clean_facts.has_active_freeze = True
    tier, reasons = evaluate_autonomy_tier(clean_facts)
    assert tier == AutonomyTier.L0
    assert any("freeze window prohibits" in r for r in reasons)


def test_l0_unhealthy_backup_blocks_automation(clean_facts):
    clean_facts.backup_healthy = False
    clean_facts.restore_point_age_hours = 48.0
    tier, reasons = evaluate_autonomy_tier(clean_facts)
    assert tier == AutonomyTier.L0
    assert any("exceeds RPO (48.0h)" in r for r in reasons)


def test_l0_missing_backup_blocks_automation(clean_facts):
    clean_facts.backup_healthy = False
    clean_facts.restore_point_age_hours = None
    tier, reasons = evaluate_autonomy_tier(clean_facts)
    assert tier == AutonomyTier.L0
    assert any("exceeds RPO (missing)" in r for r in reasons)


def test_l0_massive_blast_radius_blocks_automation(clean_facts):
    clean_facts.blast_radius.downstream_service_count = 6
    tier, reasons = evaluate_autonomy_tier(clean_facts)
    assert tier == AutonomyTier.L0
    assert any("exceeds hard safety limit (5 services)" in r for r in reasons)


def test_l0_critically_low_confidence_blocks_automation(clean_facts):
    clean_facts.confidence = 0.55
    tier, reasons = evaluate_autonomy_tier(clean_facts)
    assert tier == AutonomyTier.L0
    assert any("below minimum threshold (0.60)" in r for r in reasons)


# --- L1 Semi-Autonomous / Approval Required Tests ---

def test_l1_stale_data_requires_human_approval(clean_facts):
    clean_facts.is_stale = True
    tier, reasons = evaluate_autonomy_tier(clean_facts)
    assert tier == AutonomyTier.L1
    assert any("telemetry data is stale" in r for r in reasons)


def test_l1_confidence_below_auto_threshold_requires_approval(clean_facts):
    clean_facts.confidence = 0.85  # Between 0.60 and 0.90
    tier, reasons = evaluate_autonomy_tier(clean_facts, min_confidence_for_auto=0.90)
    assert tier == AutonomyTier.L1
    assert any("below threshold for full automation (0.90)" in r for r in reasons)


def test_l1_moderate_blast_radius_requires_approval(clean_facts):
    clean_facts.blast_radius.downstream_service_count = 2
    tier, reasons = evaluate_autonomy_tier(clean_facts, max_blast_radius_services=2)
    assert tier == AutonomyTier.L1
    assert any("Blast radius impacts 2 downstream services" in r for r in reasons)


def test_l1_active_change_window_requires_approval(clean_facts):
    clean_facts.has_active_change = True
    tier, reasons = evaluate_autonomy_tier(clean_facts)
    assert tier == AutonomyTier.L1
    assert any("Active scheduled change window present" in r for r in reasons)


def test_l1_known_exploited_vulnerability_requires_approval(clean_facts):
    clean_facts.has_exploited_vuln = True
    tier, reasons = evaluate_autonomy_tier(clean_facts)
    assert tier == AutonomyTier.L1
    assert any("Known critical exploited vulnerability" in r for r in reasons)


# --- Graph Extraction (compute_ci_risk) Tests with Mocks ---

def test_compute_ci_risk_successful_graph_query():
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    # Mock responses for CYPHER_BLAST_RADIUS and CYPHER_CI_PROVENANCE_AND_TIER
    blast_res = {
        "ci_name": "mypcpoc",
        "ci_count": 2,
        "services": ["CoreService"],
        "service_count": 1,
    }
    prov_res = {
        "name": "mypcpoc",
        "is_stale": False,
        "confidence": 1.0,
        "ci_tier": "Tier 2",
        "has_freeze": False,
        "has_change": False,
        "has_vuln": False,
        "backup_age": 6.5,
        "svc_tier": "Tier 2",
    }

    mock_session.execute_read.side_effect = [blast_res, prov_res]

    facts = compute_ci_risk(mock_driver, ci_uid="t1:vm-123", rpo_hours=24)
    assert facts.ci_name == "mypcpoc"
    assert facts.blast_radius.downstream_ci_count == 2
    assert facts.blast_radius.downstream_service_count == 1
    assert facts.backup_healthy is True
    assert facts.restore_point_age_hours == 6.5
    assert facts.autonomy_tier == AutonomyTier.L2


def test_compute_ci_risk_empty_graph_results():
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    mock_session.execute_read.side_effect = [None, None]

    facts = compute_ci_risk(mock_driver, ci_uid="t1:unknown-vm")
    assert facts.ci_name == "t1:unknown-vm"
    assert facts.blast_radius.downstream_ci_count == 0
    assert facts.is_tier1 is False
    assert facts.autonomy_tier == AutonomyTier.L2


def test_compute_ci_risk_tier1_detection():
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    blast_res = {"ci_name": "db-prod", "ci_count": 1, "services": [], "service_count": 0}
    prov_res = {
        "name": "db-prod",
        "is_stale": False,
        "confidence": 1.0,
        "ci_tier": "1",
        "has_freeze": False,
        "has_change": False,
        "has_vuln": False,
        "backup_age": 30.0,  # Exceeds 24h RPO
        "svc_tier": "Tier 1",
    }

    mock_session.execute_read.side_effect = [blast_res, prov_res]

    facts = compute_ci_risk(mock_driver, ci_uid="t1:db-prod", rpo_hours=24)
    assert facts.is_tier1 is True
    assert facts.backup_healthy is False
    assert facts.autonomy_tier == AutonomyTier.L0
