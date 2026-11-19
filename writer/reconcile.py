"""Nightly/periodic stale node reconciler enforcing freshness policies."""

from datetime import datetime, timedelta, timezone
import logging
from neo4j import Driver
from writer.cypher import MARK_STALE_CIS

logger = logging.getLogger("writer.reconcile")


def reconcile_stale_cis(
    driver: Driver,
    tenant_id: str = "t1",
    staleness_minutes: int = 60,
) -> int:
    """Mark CIs as stale if their last_seen timestamp exceeds the freshness policy threshold."""
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(minutes=staleness_minutes)
    threshold_str = threshold.isoformat()

    with driver.session() as session:
        record = session.execute_write(
            lambda tx: tx.run(
                MARK_STALE_CIS,
                tenant_id=tenant_id,
                stale_threshold=threshold_str,
            ).single()
        )
        stale_count = int(record["stale_count"]) if record else 0

    if stale_count > 0:
        logger.info(
            "Reconciled %d stale CIs for tenant %s (last_seen older than %s)",
            stale_count,
            tenant_id,
            threshold_str,
        )
    else:
        logger.debug("No stale CIs detected for tenant %s", tenant_id)

    return stale_count
