"""FastMCP Context Graph Server.

Implements the read-only Model Context Protocol (MCP) server over Streamable HTTP (/mcp).
Exposes the 6 estate context tools for BigFix AEX Agentic Remediation POC.
Enforces Hard Safety Rules 4, 5, and 6:
- ClusterIP:3001, private only, zero public ingress (Rule 4)
- Fixed parameterized Cypher read transactions only (Rule 5)
- tenant_id derived strictly from authenticated Bearer token (Rule 6)
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import os
import sys
import time
from typing import Any, AsyncIterator, Dict, List, Optional
import asyncpg
from fastmcp import FastMCP
from neo4j import AsyncDriver, AsyncGraphDatabase
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from context_graph.audit import record_audit_log, set_audit_pool
from context_graph.auth import BearerAuthMiddleware, get_current_actor, get_current_tenant
from context_graph.models import (
    BackupStatusInput,
    BlastRadiusInput,
    GetCIContextInput,
    OwnerAndRouteInput,
    RecentChangesInput,
    SimilarIncidentsInput,
)
from context_graph.tools.backup_status import execute_backup_status
from context_graph.tools.blast_radius import execute_blast_radius
from context_graph.tools.ci_context import execute_get_ci_context
from context_graph.tools.owner_and_route import execute_owner_and_route
from context_graph.tools.recent_changes import execute_recent_changes
from context_graph.tools.similar_incidents import execute_similar_incidents

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Global driver and database pool references
_neo4j_driver: Optional[AsyncDriver] = None
_db_pool: Optional[asyncpg.Pool] = None


def get_neo4j_driver() -> AsyncDriver:
    """Return the active Neo4j async driver."""
    global _neo4j_driver
    if _neo4j_driver is None:
        uri = os.getenv("NEO4J_URI", "bolt://context-graph.context-graph.svc.cluster.local:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")

        auth_file = os.getenv("NEO4J_AUTH_FILE", "/mnt/secrets-store/neo4j-auth")
        if not password and os.path.exists(auth_file):
            try:
                with open(auth_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if "/" in content:
                        parts = content.split("/", 1)
                        user, password = parts[0], parts[1]
                    else:
                        password = content
            except Exception as e:
                logger.warning("Failed to parse Neo4j auth file %s: %s", auth_file, e)

        password = password or "test_neo4j_password"
        _neo4j_driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    return _neo4j_driver


def set_neo4j_driver(driver: Optional[AsyncDriver]) -> None:
    """Set the active Neo4j driver (for testing/mocking)."""
    global _neo4j_driver
    _neo4j_driver = driver


async def get_db_pool() -> asyncpg.Pool:
    """Return the active PostgreSQL asyncpg connection pool."""
    global _db_pool
    if _db_pool is None:
        host = os.getenv("PGHOST", "psql-contextgraph-nonprod-hf3i3.postgres.database.azure.com")
        database = os.getenv("PGDATABASE", "contextgraph")
        user = os.getenv("PGUSER", "psqladmin")
        password = os.getenv("PGPASSWORD")
        port = int(os.getenv("PGPORT", "5432"))

        auth_file = os.getenv("POSTGRES_AUTH_FILE", "/mnt/secrets-store/postgres-auth")
        if os.path.exists(auth_file):
            try:
                with open(auth_file, "r", encoding="utf-8") as f:
                    data = json.loads(f.read().strip())
                    host = data.get("host", host)
                    database = data.get("database", database)
                    user = data.get("username", user)
                    password = data.get("password", password)
            except Exception as e:
                logger.warning("Failed to parse Postgres auth file %s: %s", auth_file, e)

        _db_pool = await asyncpg.create_pool(
            host=host,
            database=database,
            user=user,
            password=password,
            port=port,
            ssl="require" if "azure.com" in host else False,
            min_size=2,
            max_size=10,
        )
        set_audit_pool(_db_pool)
    return _db_pool


def set_db_pool(pool: Optional[asyncpg.Pool]) -> None:
    """Set the active asyncpg connection pool (for testing/mocking)."""
    global _db_pool
    _db_pool = pool
    set_audit_pool(pool)


# Initialize FastMCP Server instance
mcp_server = FastMCP(
    name="context-graph-mcp",
    instructions="Read-only Estate Context Graph MCP Server for BigFix AEX Agentic Remediation",
)


# ==============================================================================
# Tool 1: get_ci_context
# ==============================================================================
@mcp_server.tool()
async def get_ci_context(ci: str) -> Dict[str, Any]:
    """Retrieve Configuration Item metadata, environment tier, supporting business service,
    operational ownership group, confidence score, and staleness indicator.

    WHEN TO USE:
    Call during initial incident triage to determine CI properties, environment tier,
    and business service context before initiating remediation.

    PARAMETERS:
    - ci: Configuration Item identifier (canonical UUID or hostname, e.g. 'mypcpoc').
    """
    validated = GetCIContextInput(ci=ci)
    tenant_id = get_current_tenant()
    actor = get_current_actor()
    driver = get_neo4j_driver()

    t0 = time.perf_counter()
    result = await execute_get_ci_context(driver=driver, tenant_id=tenant_id, ci=validated.ci)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    await record_audit_log(
        tenant_id=tenant_id,
        actor=actor,
        tool_name="get_ci_context",
        entity_id=validated.ci,
        args={"ci": validated.ci},
        result_count=1 if result.get("found") else 0,
        latency_ms=latency_ms,
    )
    return result


# ==============================================================================
# Tool 2: blast_radius
# ==============================================================================
@mcp_server.tool()
async def blast_radius(ci: str, hops: int = 2) -> Dict[str, Any]:
    """Evaluate downstream blast radius up to 3 graph hops for a Configuration Item.
    Traces downstream dependency and network connectivity paths, enumerating affected CIs,
    supporting business services, and determining whether the blast radius is within safe automation limits.

    WHEN TO USE:
    Call before executing any disruptive remediation action (such as VM reboot, service restart,
    disk cleanup, or patch application) to check if downstream services will be impacted.

    PARAMETERS:
    - ci: Configuration Item identifier (canonical UUID or hostname).
    - hops: Traversal depth in hops (1 to 3, default: 2).
    """
    validated = BlastRadiusInput(ci=ci, hops=hops)
    tenant_id = get_current_tenant()
    actor = get_current_actor()
    driver = get_neo4j_driver()

    t0 = time.perf_counter()
    result = await execute_blast_radius(driver=driver, tenant_id=tenant_id, ci=validated.ci, hops=validated.hops)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    await record_audit_log(
        tenant_id=tenant_id,
        actor=actor,
        tool_name="blast_radius",
        entity_id=validated.ci,
        args={"ci": validated.ci, "hops": validated.hops},
        result_count=result.get("downstream_ci_count", 0),
        latency_ms=latency_ms,
    )
    return result


# ==============================================================================
# Tool 3: recent_changes
# ==============================================================================
@mcp_server.tool()
async def recent_changes(ci: str, hours: int = 24) -> Dict[str, Any]:
    """Retrieve recent change requests, maintenance windows, active change freezes,
    and concurrent incidents on a target Configuration Item and its 1-hop infrastructure neighbors.

    WHEN TO USE:
    Call during root cause analysis or pre-remediation checks to determine if recent changes,
    patches, or change freeze windows correlate with current alert symptoms.

    PARAMETERS:
    - ci: Configuration Item identifier (canonical UUID or hostname).
    - hours: Lookback window in hours (1 to 168 hours / 7 days, default: 24).
    """
    validated = RecentChangesInput(ci=ci, hours=hours)
    tenant_id = get_current_tenant()
    actor = get_current_actor()
    driver = get_neo4j_driver()

    t0 = time.perf_counter()
    result = await execute_recent_changes(driver=driver, tenant_id=tenant_id, ci=validated.ci, hours=validated.hours)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    await record_audit_log(
        tenant_id=tenant_id,
        actor=actor,
        tool_name="recent_changes",
        entity_id=validated.ci,
        args={"ci": validated.ci, "hours": validated.hours},
        result_count=result.get("direct_changes_count", 0) + result.get("direct_incidents_count", 0),
        latency_ms=latency_ms,
    )
    return result


# ==============================================================================
# Tool 4: backup_status
# ==============================================================================
@mcp_server.tool()
async def backup_status(ci: str) -> Dict[str, Any]:
    """Check the backup health, last restore point timestamp, and Recovery Point Objective (RPO)
    compliance (threshold <= 24 hours) for a Configuration Item.

    WHEN TO USE:
    Call before high-risk changes or automated remediations to verify that a fresh,
    restorable recovery point exists in case rollback is required.

    PARAMETERS:
    - ci: Configuration Item identifier (canonical UUID or hostname).
    """
    validated = BackupStatusInput(ci=ci)
    tenant_id = get_current_tenant()
    actor = get_current_actor()
    driver = get_neo4j_driver()

    t0 = time.perf_counter()
    result = await execute_backup_status(driver=driver, tenant_id=tenant_id, ci=validated.ci)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    await record_audit_log(
        tenant_id=tenant_id,
        actor=actor,
        tool_name="backup_status",
        entity_id=validated.ci,
        args={"ci": validated.ci},
        result_count=1 if result.get("backup_found") else 0,
        latency_ms=latency_ms,
    )
    return result


# ==============================================================================
# Tool 5: similar_incidents
# ==============================================================================
@mcp_server.tool()
async def similar_incidents(text: str, ci: Optional[str] = None, k: int = 3) -> Dict[str, Any]:
    """Perform semantic vector search using PostgreSQL pgvector to retrieve relevant
    historical incidents, root cause analyses (RCAs), and remediation runbooks.

    WHEN TO USE:
    Call when diagnosing an alert or symptom (e.g. disk space full, service hung, high memory)
    to find matching past resolutions, root cause analyses, and approved runbooks.

    PARAMETERS:
    - text: Free-text search query describing the symptom, error code, or alert title (3 to 500 chars).
    - ci: Optional Configuration Item identifier to correlate local context.
    - k: Number of similar documents to return (1 to 5, default: 3).
    """
    validated = SimilarIncidentsInput(text=text, ci=ci, k=k)
    tenant_id = get_current_tenant()
    actor = get_current_actor()
    pool = await get_db_pool()

    t0 = time.perf_counter()
    result = await execute_similar_incidents(
        pool=pool,
        tenant_id=tenant_id,
        text=validated.text,
        ci=validated.ci,
        k=validated.k,
    )
    latency_ms = (time.perf_counter() - t0) * 1000.0

    await record_audit_log(
        tenant_id=tenant_id,
        actor=actor,
        tool_name="similar_incidents",
        entity_id=validated.ci or "search",
        args={"text": validated.text, "ci": validated.ci, "k": validated.k},
        result_count=result.get("results_count", 0),
        latency_ms=latency_ms,
    )
    return result


# ==============================================================================
# Tool 6: owner_and_route
# ==============================================================================
@mcp_server.tool()
async def owner_and_route(ci: str) -> Dict[str, Any]:
    """Resolve operational ownership, primary assignment group, escalation channel/on-call path,
    and permitted automation execution engines (e.g. BigFix) for a Configuration Item.

    WHEN TO USE:
    Call to determine the accountable operations team, escalation on-call contact,
    or confirmed execution engine before executing an automation or routing an alert.

    PARAMETERS:
    - ci: Configuration Item identifier (canonical UUID or hostname).
    """
    validated = OwnerAndRouteInput(ci=ci)
    tenant_id = get_current_tenant()
    actor = get_current_actor()
    driver = get_neo4j_driver()

    t0 = time.perf_counter()
    result = await execute_owner_and_route(driver=driver, tenant_id=tenant_id, ci=validated.ci)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    await record_audit_log(
        tenant_id=tenant_id,
        actor=actor,
        tool_name="owner_and_route",
        entity_id=validated.ci,
        args={"ci": validated.ci},
        result_count=1,
        latency_ms=latency_ms,
    )
    return result


# ==============================================================================
# Starlette Application & Lifespan Assembly
# ==============================================================================
async def healthz(request: Request) -> JSONResponse:
    """Health check endpoint for AEX MCP Health Monitor and Kubernetes probes."""
    return JSONResponse({
        "status": "healthy",
        "service": "context-graph-mcp",
        "transport": "streamable-http",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tools_registered": 6,
    })


def create_app() -> Starlette:
    """Construct Starlette application wrapping FastMCP with authentication and health endpoints."""
    # Obtain base FastMCP HTTP Starlette app
    base_app = mcp_server.http_app()

    # Register /healthz probe route
    base_app.routes.append(Route("/healthz", healthz, methods=["GET"]))

    # Wrap with Bearer authentication middleware
    base_app.add_middleware(BearerAuthMiddleware, default_tenant="t1")
    return base_app


app = create_app()


def main() -> None:
    """Server entrypoint."""
    import uvicorn
    port = int(os.getenv("PORT", "3001"))
    host = os.getenv("HOST", "0.0.0.0")
    logger.info("Starting Context Graph FastMCP Server on %s:%d/mcp", host, port)
    uvicorn.run("context_graph.server:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
