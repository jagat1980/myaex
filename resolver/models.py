"""Data models for entity resolution and identity correlation."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field
from connectors.common.models import NormalisedRelation


class MatchKeyType(str, Enum):
    """Hierarchy of entity resolution match keys per docs/ontology.md."""

    CLOUD_ID = "CLOUD_ID"  # Confidence 1.00 (Azure Resource ID / vCenter UUID)
    SYS_ID = "SYS_ID"      # Confidence 0.95 (CMDB sys_id cross-reference)
    FQDN = "FQDN"          # Confidence 0.90 (Normalized FQDN)
    HOSTNAME_IP = "HOSTNAME_IP"  # Confidence 0.80 (Hostname + validated private IP)
    HOSTNAME = "HOSTNAME"  # Confidence 0.60 (Hostname only, analyzed for conflicts)


class MatchConfidence:
    """Pre-defined confidence levels adhering to ontology."""

    CLOUD_ID: float = 1.00
    SYS_ID: float = 0.95
    FQDN: float = 0.90
    HOSTNAME_IP: float = 0.80
    HOSTNAME: float = 0.60


class ResolutionResult(BaseModel):
    """Result of an entity resolution lookup."""

    ci_id: UUID
    confidence: float
    matched_key_type: MatchKeyType | None = None
    matched_key_value: str | None = None
    is_new: bool = False
    is_conflict: bool = False
    conflict_reason: str | None = None


class ResolvedEntity(BaseModel):
    """Fully resolved configuration item ready for graph ingestion."""

    tenant_id: str = "t1"
    ci_id: UUID
    uid: str  # "<tenant_id>:<ci_id>"
    kind: str  # 'VM', 'Host', etc.
    canonical_name: str
    source_system: str
    source_id: str
    confidence: float
    fqdn: str | None = None
    ip: str | None = None
    mac: str | None = None
    cloud_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    relations: list[NormalisedRelation] = Field(default_factory=list)
    observed_at: datetime
