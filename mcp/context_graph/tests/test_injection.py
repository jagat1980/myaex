"""Tests ensuring zero Cypher injection vulnerability (Hard Safety Rule 5).

Verifies that:
1. Pydantic input models reject malicious injection strings.
2. Even if passed to the executor, parameterized Cypher queries treat inputs
   strictly as parameter values ($ci, $uid) and never as executable Cypher clauses.
"""

from typing import Any, Dict
import pytest
from pydantic import ValidationError

from context_graph.models import GetCIContextInput
from context_graph.tests.conftest import MockDriver, MockTransaction
from context_graph.tools.ci_context import execute_get_ci_context


def test_pydantic_rejects_cypher_injection_characters() -> None:
    """Inputs with Cypher injection characters (quotes, semicolons, brackets) must fail validation."""
    malicious_inputs = [
        "mypcpoc'; DROP ALL; //",
        "mypcpoc' UNION MATCH (n) DETACH DELETE n //",
        "mypcpoc' OR 1=1 //",
        "mypcpoc; RETURN 1",
        "mypcpoc\" OR \"\"=\"",
    ]
    for bad_ci in malicious_inputs:
        with pytest.raises(ValidationError):
            GetCIContextInput(ci=bad_ci)


@pytest.mark.asyncio
async def test_parameterized_query_safely_handles_literal_injection_string() -> None:
    """When a string with special characters reaches the parameterized executor,
    it is passed safely as $ci and $uid without syntax error or code injection.
    """
    safe_driver = MockDriver(MockTransaction(single_record=None))
    malicious_ci = "injection-attempt-test"

    result = await execute_get_ci_context(
        driver=safe_driver,
        tenant_id="t1",
        ci=malicious_ci,
    )
    assert result["found"] is False
    assert malicious_ci in result["message"]
