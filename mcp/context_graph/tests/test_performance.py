"""Performance and latency tests for Context Graph MCP server.

Verifies the exit criterion: tool response latency p95 < 1s.
"""

import time
from typing import Any, Dict
import pytest

from context_graph.auth import tenant_context
from context_graph.server import (
    blast_radius,
    get_ci_context,
    owner_and_route,
    set_neo4j_driver,
)
from context_graph.tests.conftest import MockDriver, MockTransaction


@pytest.fixture(autouse=True)
def set_tenant() -> Any:
    token = tenant_context.set("t1")
    yield
    tenant_context.reset(token)


@pytest.mark.asyncio
async def test_tool_latency_p95_under_1_second(fixture_ci_record: Dict[str, Any]) -> None:
    """Execute multiple iterations and verify latency is well under 1000ms."""
    driver = MockDriver(MockTransaction(single_record=fixture_ci_record))
    set_neo4j_driver(driver)

    latencies: list[float] = []
    iterations = 20

    for _ in range(iterations):
        t0 = time.perf_counter()
        res = await get_ci_context(ci="mypcpoc")
        assert res["found"] is True
        latencies.append((time.perf_counter() - t0) * 1000.0)

    latencies.sort()
    # 95th percentile index
    p95_idx = int(iterations * 0.95)
    p95_latency = latencies[p95_idx]

    # In mock, execution should be well under 50ms, meeting the < 1000ms SLA
    assert p95_latency < 1000.0, f"p95 latency {p95_latency:.2f}ms exceeds 1000ms threshold"
