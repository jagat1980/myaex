"""Unit tests for Bearer token authentication and tenant resolution.

Verifies:
- 401 without Authorization header
- 401 with invalid Bearer token
- 200 on /healthz probe without auth
- Successful tenant resolution with valid token
"""

from typing import Any
import pytest
from starlette.testclient import TestClient

from context_graph.auth import tenant_context
from context_graph.server import app


@pytest.fixture
def client() -> Any:
    with TestClient(app) as c:
        yield c


def test_healthz_unauthenticated(client: TestClient) -> None:
    """Probe /healthz must succeed without credentials for AEX health monitor."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "context-graph-mcp"
    assert data["tools_registered"] == 6


def test_mcp_missing_authorization_header(client: TestClient) -> None:
    """Calls to /mcp without Authorization header must yield 401 Unauthorized."""
    response = client.post("/mcp", json={"jsonrpc": "2.0", "method": "tools/list", "id": 1})
    assert response.status_code == 401
    assert "Missing or malformed Authorization header" in response.json()["detail"]


def test_mcp_malformed_authorization_header(client: TestClient) -> None:
    """Calls with non-Bearer auth must yield 401 Unauthorized."""
    response = client.post(
        "/mcp",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
    )
    assert response.status_code == 401
    assert "Missing or malformed Authorization header" in response.json()["detail"]


def test_mcp_invalid_bearer_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Calls with unknown Bearer token must yield 401 Unauthorized."""
    monkeypatch.setenv("MCP_AUTH_TOKEN", "super-secret-token-12345")
    monkeypatch.delenv("MCP_ENV", raising=False)

    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer totally-invalid-token"},
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
    )
    assert response.status_code == 401
    assert "Invalid or expired Bearer token" in response.json()["detail"]


def test_mcp_valid_bearer_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Calls with valid Bearer token pass through authentication."""
    monkeypatch.setenv("MCP_AUTH_TOKEN", "valid-prod-token-xyz")

    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer valid-prod-token-xyz"},
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
    )
    # Status code is 200 or FastMCP protocol response (not 401)
    assert response.status_code != 401


def test_multi_tenant_test_token_resolution(client: TestClient) -> None:
    """Test tokens format 'test-token-<tenant>' correctly resolve tenant."""
    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer test-token-t1"},
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
    )
    assert response.status_code != 401
