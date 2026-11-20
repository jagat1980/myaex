"""Pydantic v2 validation models for Context Graph MCP server.

Enforces strict input validation (lengths, allowed characters, numeric bounds)
and structured compact JSON output formats (< 4k tokens) carrying source_system
and last_seen provenance per fact.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class GetCIContextInput(BaseModel):
    """Input model for get_ci_context tool."""
    ci: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-\.:/]+$",
        description="Configuration Item identifier (canonical UUID or hostname, e.g. 'mypcpoc')",
    )


class BlastRadiusInput(BaseModel):
    """Input model for blast_radius tool."""
    ci: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-\.:/]+$",
        description="Configuration Item identifier to evaluate blast radius from",
    )
    hops: int = Field(
        default=2,
        ge=1,
        le=3,
        description="Downstream graph traversal depth (1 to 3 hops)",
    )


class RecentChangesInput(BaseModel):
    """Input model for recent_changes tool."""
    ci: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-\.:/]+$",
        description="Configuration Item identifier to check for changes and incidents",
    )
    hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Lookback window in hours (1 to 168 hours / 7 days)",
    )


class BackupStatusInput(BaseModel):
    """Input model for backup_status tool."""
    ci: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-\.:/]+$",
        description="Configuration Item identifier to check backup health and RPO compliance",
    )


class SimilarIncidentsInput(BaseModel):
    """Input model for similar_incidents tool."""
    text: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Search query describing the incident symptoms, error message, or log snippet",
    )
    ci: Optional[str] = Field(
        default=None,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-\.:/]+$",
        description="Optional CI identifier to correlate context",
    )
    k: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Number of similar documents to return (1 to 5)",
    )


class OwnerAndRouteInput(BaseModel):
    """Input model for owner_and_route tool."""
    ci: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-\.:/]+$",
        description="Configuration Item identifier to resolve operational ownership and routing",
    )
