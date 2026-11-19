"""Stage 3 execution entrypoint: Entity Resolution and Temporal Graph Writing."""

import asyncio
from datetime import datetime, timezone
import logging
import os
import sys
from connectors.common.db import create_db_pool
from resolver.engine import ResolutionEngine
from writer.client import Neo4jWriterClient
from writer.graph_writer import TemporalGraphWriter
from writer.reconcile import reconcile_stale_cis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("writer.main")


async def run_pipeline() -> bool:
    """Execute the full Stage 3 pipeline: Resolve identities -> Upsert graph -> Reconcile."""
    tenant_id = os.getenv("TENANT_ID", "t1")
    staleness_minutes = int(os.getenv("STALENESS_MINUTES", "60"))
    sync_started_at = datetime.now(timezone.utc)

    logger.info("Starting Stage 3 sync cycle for tenant: %s", tenant_id)

    # 1. Entity Resolution
    pg_pool = await create_db_pool()
    try:
        async with pg_pool.acquire() as conn:
            engine = ResolutionEngine(conn=conn, tenant_id=tenant_id)
            resolved_entities = await engine.run()
    finally:
        await pg_pool.close()

    logger.info("Resolved %d configuration items", len(resolved_entities))

    # 2. Temporal Graph Writing
    with Neo4jWriterClient() as neo4j_client:
        driver = neo4j_client.get_driver()
        writer = TemporalGraphWriter(driver=driver)

        metrics = writer.write_entities(
            entities=resolved_entities,
            sync_started_at=sync_started_at,
        )
        logger.info(
            "Graph ingestion metrics: nodes=%d, edges=%d, closed_edges=%d",
            metrics["nodes"],
            metrics["edges"],
            metrics["edges_closed"],
        )

        # 3. Freshness Reconciliation
        stale_count = reconcile_stale_cis(
            driver=driver,
            tenant_id=tenant_id,
            staleness_minutes=staleness_minutes,
        )

        # 4. Final Graph Census
        census = writer.get_graph_counts(tenant_id=tenant_id)
        logger.info(
            "Final Estate Context Graph state: %d total CIs, %d total edges in Neo4j",
            census["nodes"],
            census["edges"],
        )

    return True


def main() -> None:
    """CLI / Container Entrypoint."""
    try:
        success = asyncio.run(run_pipeline())
        if not success:
            sys.exit(1)
    except Exception as exc:
        logger.exception("Stage 3 pipeline execution failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
