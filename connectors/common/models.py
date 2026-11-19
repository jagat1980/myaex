"""Common data models for Context Graph source connectors."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class NormalisedRelation(BaseModel):
    """Normalized edge/relationship between CIs."""

    type: str  # e.g., 'RUNS_ON', 'DEPENDS_ON', 'CONNECTS_TO'
    target_source_system: str
    target_source_id: str
    target_kind: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class NormalisedRecord(BaseModel):
    """Normalized configuration item record emitted by all source connectors."""

    tenant_id: str = "t1"
    source_system: str  # e.g., 'azure', 'solarwinds'
    source_id: str  # Unique ID in source system
    kind: str  # 'VM', 'Host', 'NIC', 'Disk'
    name: str
    fqdn: str | None = None
    ip: str | None = None
    mac: str | None = None
    cloud_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    relations: list[NormalisedRelation] = Field(default_factory=list)
    observed_at: datetime


class IngestRunResult(BaseModel):
    """Run metrics and execution status for an ingestion cycle."""

    tenant_id: str = "t1"
    source_system: str
    watermark: str | None = None
    records_read: int = 0
    records_new: int = 0
    records_changed: int = 0
    errors: int = 0
    started_at: datetime
    finished_at: datetime | None = None
    status: str = "RUNNING"  # 'SUCCESS', 'FAILED', 'PARTIAL'
