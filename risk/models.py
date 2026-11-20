"""Data models for deterministic risk evaluation and vector intelligence."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, Field


class AutonomyTier(str, Enum):
    """Autonomy tiers for BigFix AEX agentic remediation actions."""

    L0 = "L0"  # Manual execution only. Automated remediation is blocked.
    L1 = "L1"  # Semi-autonomous. Action requires explicit human approval before execution.
    L2 = "L2"  # Full autonomy. Agentic action executes automatically without a human gate.


class BlastRadius(BaseModel):
    """Downstream dependency footprint from graph traversal."""

    downstream_ci_count: int = 0
    downstream_service_count: int = 0
    downstream_services: list[str] = Field(default_factory=list)
    max_hops: int = 3


class RiskFacts(BaseModel):
    """Deterministic operational facts extracted from graph and database."""

    ci_uid: str
    ci_name: str
    tenant_id: str = "t1"
    blast_radius: BlastRadius = Field(default_factory=BlastRadius)
    is_tier1: bool = False
    has_active_change: bool = False
    has_active_freeze: bool = False
    restore_point_age_hours: float | None = None
    backup_healthy: bool = True
    has_exploited_vuln: bool = False
    is_stale: bool = False
    confidence: float = 1.0
    autonomy_tier: AutonomyTier = AutonomyTier.L2
    autonomy_reasons: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VectorDocument(BaseModel):
    """Document payload for historical incident, RCA, or runbook."""

    tenant_id: str = "t1"
    doc_id: str
    doc_type: str  # 'incident', 'rca', 'runbook'
    title: str
    content: str
    service_name: str | None = None
    ci_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """pgvector cosine similarity search result."""

    id: int
    tenant_id: str
    doc_type: str
    content: str
    service_name: str | None = None
    ci_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    similarity: float
