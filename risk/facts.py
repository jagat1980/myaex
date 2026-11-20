"""Deterministic risk assessment engine computing facts from graph and database.

Hard Safety Rule 5: Zero dynamic/LLM-generated Cypher. Read transactions only.
Deterministic autonomy mapping: L0 (Manual), L1 (Approval), L2 (Full Autonomy).
"""

from datetime import datetime, timezone
import logging
from typing import Any
from neo4j import Driver
from risk.models import AutonomyTier, BlastRadius, RiskFacts

logger = logging.getLogger("risk.facts")


def evaluate_autonomy_tier(
    facts: RiskFacts,
    min_confidence_for_auto: float = 0.90,
    max_blast_radius_services: int = 2,
) -> tuple[AutonomyTier, list[str]]:
    """Pure, deterministic autonomy tier evaluator strictly following signed-off policy.
    
    Returns (AutonomyTier, list of reasons).
    """
    l0_reasons: list[str] = []
    l1_reasons: list[str] = []

    # --- 1. L0 Hard Blocks (Automation Prohibited) ---
    if facts.is_tier1:
        l0_reasons.append("Target CI or dependent downstream service is Tier 1 mission-critical.")

    if facts.has_active_freeze:
        l0_reasons.append("Active change freeze window prohibits all automated remediation.")

    if not facts.backup_healthy:
        age_str = f"{facts.restore_point_age_hours:.1f}h" if facts.restore_point_age_hours is not None else "missing"
        l0_reasons.append(f"Backup restore point is unhealthy or exceeds RPO ({age_str}).")

    if facts.blast_radius.downstream_service_count > 5:
        l0_reasons.append(
            f"Downstream service blast radius ({facts.blast_radius.downstream_service_count}) "
            "exceeds hard safety limit (5 services)."
        )

    if facts.confidence < 0.60:
        l0_reasons.append(
            f"Identity resolution confidence ({facts.confidence:.2f}) is below minimum threshold (0.60)."
        )

    if l0_reasons:
        return AutonomyTier.L0, l0_reasons

    # --- 2. L1 Semi-Autonomous (Human Approval Required) ---
    if facts.is_stale:
        l1_reasons.append("CI telemetry data is stale; human verification required before execution.")

    if facts.confidence < min_confidence_for_auto:
        l1_reasons.append(
            f"Identity confidence ({facts.confidence:.2f}) is below threshold for full automation ({min_confidence_for_auto:.2f})."
        )

    if facts.blast_radius.downstream_service_count >= max_blast_radius_services:
        l1_reasons.append(
            f"Blast radius impacts {facts.blast_radius.downstream_service_count} downstream services "
            f"(threshold: {max_blast_radius_services})."
        )

    if facts.has_active_change:
        l1_reasons.append("Active scheduled change window present on CI or service.")

    if facts.has_exploited_vuln:
        l1_reasons.append("Known critical exploited vulnerability (KEV) flagged on CI.")

    if l1_reasons:
        return AutonomyTier.L1, l1_reasons

    # --- 3. L2 Full Autonomy Permitted ---
    return AutonomyTier.L2, ["All safety invariants satisfied for autonomous execution."]


CYPHER_BLAST_RADIUS = """
MATCH (start:CI {uid: $uid})
OPTIONAL MATCH (start)-[*1..3]->(downstream:CI)
WITH start, count(DISTINCT downstream) AS ci_count
OPTIONAL MATCH (start)-[*1..3]->(svc:BusinessService)
RETURN start.name AS ci_name,
       ci_count,
       collect(DISTINCT svc.name) AS services,
       count(DISTINCT svc) AS service_count
"""

CYPHER_CI_PROVENANCE_AND_TIER = """
MATCH (c:CI {uid: $uid})
OPTIONAL MATCH (c)-[:SUPPORTS]->(s:BusinessService)
RETURN c.name AS name,
       c.stale AS is_stale,
       c.confidence AS confidence,
       c.tier AS ci_tier,
       c.has_active_freeze AS has_freeze,
       c.has_active_change AS has_change,
       c.has_exploited_vuln AS has_vuln,
       c.restore_point_age_hours AS backup_age,
       s.tier AS svc_tier
"""


def compute_ci_risk(
    driver: Driver,
    ci_uid: str,
    tenant_id: str = "t1",
    rpo_hours: int = 24,
    min_confidence_for_auto: float = 0.90,
) -> RiskFacts:
    """Extract graph facts and compute the deterministic autonomy tier for a CI."""
    with driver.session() as session:
        # 1. Query Blast Radius
        blast_record = session.execute_read(
            lambda tx: tx.run(CYPHER_BLAST_RADIUS, uid=ci_uid).single()
        )

        ci_name = ci_uid
        downstream_cis = 0
        downstream_services: list[str] = []
        downstream_svc_count = 0

        if blast_record and blast_record["ci_name"]:
            ci_name = str(blast_record["ci_name"])
            downstream_cis = int(blast_record["ci_count"] or 0)
            downstream_services = [s for s in blast_record["services"] if s]
            downstream_svc_count = len(downstream_services)

        blast = BlastRadius(
            downstream_ci_count=downstream_cis,
            downstream_service_count=downstream_svc_count,
            downstream_services=downstream_services,
            max_hops=3,
        )

        # 2. Query CI Provenance, Tier, and Operational Flags
        prov_record = session.execute_read(
            lambda tx: tx.run(CYPHER_CI_PROVENANCE_AND_TIER, uid=ci_uid).single()
        )

        is_stale = False
        confidence = 1.0
        is_tier1 = False
        has_freeze = False
        has_change = False
        has_vuln = False
        backup_age_hours: float | None = None
        backup_healthy = True

        if prov_record:
            if prov_record["name"]:
                ci_name = str(prov_record["name"])
            is_stale = bool(prov_record["is_stale"])
            if prov_record["confidence"] is not None:
                confidence = float(prov_record["confidence"])

            # Check Tier 1
            ci_tier = str(prov_record["ci_tier"] or "").lower()
            svc_tier = str(prov_record["svc_tier"] or "").lower()
            if "1" in ci_tier or "1" in svc_tier or "tier 1" in ci_tier or "tier 1" in svc_tier:
                is_tier1 = True

            has_freeze = bool(prov_record["has_freeze"])
            has_change = bool(prov_record["has_change"])
            has_vuln = bool(prov_record["has_vuln"])

            # Backup RPO
            raw_age = prov_record["backup_age"]
            if raw_age is not None:
                backup_age_hours = float(raw_age)
                backup_healthy = backup_age_hours <= rpo_hours

    facts = RiskFacts(
        ci_uid=ci_uid,
        ci_name=ci_name,
        tenant_id=tenant_id,
        blast_radius=blast,
        is_tier1=is_tier1,
        has_active_change=has_change,
        has_active_freeze=has_freeze,
        restore_point_age_hours=backup_age_hours,
        backup_healthy=backup_healthy,
        has_exploited_vuln=has_vuln,
        is_stale=is_stale,
        confidence=confidence,
    )

    tier, reasons = evaluate_autonomy_tier(
        facts=facts,
        min_confidence_for_auto=min_confidence_for_auto,
    )
    facts.autonomy_tier = tier
    facts.autonomy_reasons = reasons

    return facts
