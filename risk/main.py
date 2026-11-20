"""Stage 4 CLI / Job entrypoint: Load pgvector embeddings and evaluate graph risk."""

import asyncio
import logging
import os
import sys
from connectors.common.db import create_db_pool
from risk.facts import compute_ci_risk
from risk.loader import load_seed_documents
from risk.vectors import VectorStore
from writer.client import Neo4jWriterClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("risk.main")


async def run_stage4_pipeline() -> bool:
    """Execute Stage 4 intelligence loading and risk assessment validation."""
    tenant_id = os.getenv("TENANT_ID", "t1")
    rpo_hours = int(os.getenv("RPO_HOURS", "24"))
    min_conf = float(os.getenv("MIN_CONFIDENCE_FOR_AUTO", "0.90"))

    logger.info("Starting Stage 4 pgvector loading and risk validation for tenant: %s", tenant_id)

    # 1. Load pgvector Seed Documents
    pg_pool = await create_db_pool()
    try:
        async with pg_pool.acquire() as conn:
            loaded_count = await load_seed_documents(conn, tenant_id=tenant_id)
            logger.info("Loaded %d documents into pgvector embeddings table", loaded_count)

            # Validate Similarity Search
            v_store = VectorStore(conn)
            test_query = "Windows C drive disk space 100% full CBS log cleanup"
            logger.info("Executing test semantic search for: '%s'", test_query)
            search_results = await v_store.search_similar(
                tenant_id=tenant_id,
                query_text=test_query,
                k=3,
            )
            for res in search_results:
                logger.info(
                    "Top match: [%s] %s (similarity: %.4f)",
                    res.doc_type,
                    res.metadata.get("title", res.content[:40]),
                    res.similarity,
                )
    finally:
        await pg_pool.close()

    # 2. Evaluate Graph Risk on Live CIs in Neo4j
    with Neo4jWriterClient() as neo4j_client:
        driver = neo4j_client.get_driver()
        with driver.session() as session:
            vms = session.execute_read(
                lambda tx: tx.run("MATCH (c:CI:VM {tenant_id: $tenant_id}) RETURN c.uid AS uid, c.name AS name", tenant_id=tenant_id).data()
            )

        logger.info("Evaluating risk for %d live VMs in Neo4j...", len(vms))
        for vm in vms:
            uid = vm["uid"]
            facts = compute_ci_risk(
                driver=driver,
                ci_uid=uid,
                tenant_id=tenant_id,
                rpo_hours=rpo_hours,
                min_confidence_for_auto=min_conf,
            )
            logger.info(
                "Risk Evaluation for %s (UID: %s) -> Autonomy Tier: %s | Blast Radius: %d CIs, %d Services | Reasons: %s",
                facts.ci_name,
                facts.ci_uid,
                facts.autonomy_tier.value,
                facts.blast_radius.downstream_ci_count,
                facts.blast_radius.downstream_service_count,
                facts.autonomy_reasons,
            )

    logger.info("Stage 4 pipeline execution completed successfully.")
    return True


def main() -> None:
    """CLI entrypoint."""
    try:
        success = asyncio.run(run_stage4_pipeline())
        if not success:
            sys.exit(1)
    except Exception as exc:
        logger.exception("Stage 4 pipeline failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
