"""Shared library for Context Graph connectors."""

from connectors.common.models import NormalisedRecord, NormalisedRelation, IngestRunResult
from connectors.common.hasher import compute_content_hash
from connectors.common.watermark import get_latest_watermark, format_iso_watermark
from connectors.common.db import (
    create_db_pool,
    upsert_raw_record,
    start_ingest_run,
    finish_ingest_run,
)

__all__ = [
    "NormalisedRecord",
    "NormalisedRelation",
    "IngestRunResult",
    "compute_content_hash",
    "get_latest_watermark",
    "format_iso_watermark",
    "create_db_pool",
    "upsert_raw_record",
    "start_ingest_run",
    "finish_ingest_run",
]
