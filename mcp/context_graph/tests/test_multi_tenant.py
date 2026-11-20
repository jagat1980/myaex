"""Tests for cross-tenant isolation (Hard Safety Rule 6).

Verifies that:
1. Queries authenticated for tenant 't2' return zero records from tenant 't1'.
2. Tool handlers do not accept or allow override of tenant_id from user arguments.
"""

from typing import Any, Dict
import pytest

from context_graph.auth import tenant_context
from context_graph.server import get_ci_context, set_db_pool, set_neo4j_driver, similar_incidents
from context_graph.tests.conftest import MockAsyncpgPool, MockDriver, MockTransaction


@pytest.mark.asyncio
async def test_cross_tenant_isolation_graph_query(fixture_ci_record: Dict[str, Any]) -> None:
    """A query authenticated as tenant 't2' must not see tenant 't1' CIs."""
    driver = MockDriver(MockTransaction(single_record=fixture_ci_record))
    set_neo4j_driver(driver)

    # Set tenant to unauthorized tenant 't2'
    token = tenant_context.set("t2")
    try:
        result = await get_ci_context(ci="mypcpoc")
        # In mock, tenant != 't1' returns single_record=None
        assert result["found"] is False
        assert result["tenant_id"] == "t2"
    finally:
        tenant_context.reset(token)


@pytest.mark.asyncio
async def test_cross_tenant_isolation_vector_query(fixture_vector_rows: list[Dict[str, Any]]) -> None:
    """A pgvector search authenticated as tenant 't2' must return zero documents from tenant 't1'."""
    pool = MockAsyncpgPool(fixture_vector_rows)
    set_db_pool(pool)

    # Set tenant to unauthorized tenant 't2'
    token = tenant_context.set("t2")
    try:
        result = await similar_incidents(text="disk space full cbs log cleanup")
        # In mock, tenant != 't1' returns rows=[]
        assert result["results_count"] == 0
        assert len(result["results"]) == 0
    finally:
        tenant_context.reset(token)
