"""Pytest fixtures and mock objects for Context Graph MCP server tests."""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock
import pytest

from context_graph.server import set_db_pool, set_neo4j_driver


class MockNeo4jRecord:
    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)


class MockCursor:
    def __init__(self, single_record: Optional[Dict[str, Any]] = None, multi_records: Optional[List[Dict[str, Any]]] = None) -> None:
        self._single = MockNeo4jRecord(single_record) if single_record is not None else None
        self._multi = multi_records or []

    async def single(self) -> Optional[MockNeo4jRecord]:
        return self._single

    async def data(self) -> List[Dict[str, Any]]:
        return self._multi


class MockTransaction:
    def __init__(self, single_record: Optional[Dict[str, Any]] = None, multi_records: Optional[List[Dict[str, Any]]] = None) -> None:
        self.single_record = single_record
        self.multi_records = multi_records

    async def run(self, query: str, **params: Any) -> MockCursor:
        # Check if tenant isolation filtering is requested
        tenant_id = params.get("tenant_id")
        if tenant_id and tenant_id != "t1":
            # Cross-tenant query: return empty
            return MockCursor(single_record=None, multi_records=[])
        return MockCursor(single_record=self.single_record, multi_records=self.multi_records)


class MockSession:
    def __init__(self, tx: MockTransaction) -> None:
        self.tx = tx

    async def __aenter__(self) -> "MockSession":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    async def execute_read(self, callback: Any, **kwargs: Any) -> Any:
        return await callback(self.tx, **kwargs)


class MockDriver:
    def __init__(self, tx: MockTransaction) -> None:
        self.tx = tx

    def session(self) -> MockSession:
        return MockSession(self.tx)

    async def close(self) -> None:
        pass


class MockAsyncpgConnection:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self.rows = rows

    async def fetch(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        # Check tenant_id parameter (usually $2 in similar_documents)
        if len(args) >= 2 and args[1] != "t1":
            return []
        return self.rows

    async def execute(self, query: str, *args: Any) -> str:
        return "INSERT 0 1"


class MockAsyncpgPool:
    def __init__(self, rows: Optional[List[Dict[str, Any]]] = None) -> None:
        self.rows = rows or []
        self.conn = MockAsyncpgConnection(self.rows)

    def acquire(self) -> Any:
        conn = self.conn

        class PoolAcquireContext:
            async def __aenter__(self) -> MockAsyncpgConnection:
                return conn

            async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
                pass

        return PoolAcquireContext()

    async def close(self) -> None:
        pass


@pytest.fixture
def fixture_ci_record() -> Dict[str, Any]:
    return {
        "uid": "t1:46e8ff7b-80fb-493d-a3c4-613feafb4177",
        "name": "mypcpoc",
        "labels": ["CI", "VM"],
        "type": "VM",
        "env": "non-production",
        "tier": "Tier-2",
        "confidence": 1.0,
        "stale": False,
        "last_seen": "2026-11-20T10:00:00Z",
        "source_system": "azure",
        "service_name": "POC-Portal",
        "service_tier": "Tier-2",
        "owner_group": "CloudOps-Windows",
    }


@pytest.fixture
def fixture_blast_radius_records() -> List[Dict[str, Any]]:
    return [
        {
            "uid": "t1:nic-237",
            "name": "mypcpoc237_z1",
            "labels": ["CI", "NetworkDevice"],
            "type": "NetworkDevice",
            "tier": "Standard",
            "source_system": "azure",
            "last_seen": "2026-11-20T10:00:00Z",
            "distance": 1,
            "services": ["POC-Portal"],
        },
        {
            "uid": "t1:disk-01",
            "name": "mypcpoc_OsDisk_1",
            "labels": ["CI", "Disk"],
            "type": "Disk",
            "tier": "Standard",
            "source_system": "azure",
            "last_seen": "2026-11-20T10:00:00Z",
            "distance": 1,
            "services": [],
        },
    ]


@pytest.fixture
def fixture_vector_rows() -> List[Dict[str, Any]]:
    return [
        {
            "id": 1,
            "ci_id": None,
            "service_name": None,
            "doc_type": "incident",
            "content": "C: drive reached 98% disk capacity. Investigation revealed CBS log accumulation.",
            "metadata": json.dumps({"doc_id": "INC-1001", "title": "C: Drive 98% full on Windows VM mypcpoc due to CBS accumulation", "source_system": "itsm"}),
            "similarity": 0.8950,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "id": 2,
            "ci_id": None,
            "service_name": None,
            "doc_type": "runbook",
            "content": "1. Run DISM /online /cleanup-image /startcomponentcleanup. 2. Purge CBS logs.",
            "metadata": json.dumps({"doc_id": "RB-3001", "title": "Runbook: Safe Windows OS Disk Cleanup", "source_system": "runbook"}),
            "similarity": 0.8420,
            "created_at": datetime.now(timezone.utc),
        },
    ]
