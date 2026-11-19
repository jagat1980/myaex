"""Azure Resource Graph connector entrypoint."""

import asyncio
from datetime import datetime, timezone
import logging
import os
import sys
from connectors.azure.client import AzureResourceGraphReader
from connectors.azure.extract import (
    VM_QUERY,
    NIC_QUERY,
    build_nic_index,
    map_vm_to_normalised_record,
)
from connectors.common.db import (
    create_db_pool,
    upsert_raw_record,
    start_ingest_run,
    finish_ingest_run,
)
from connectors.common.models import IngestRunResult
from connectors.common.watermark import format_iso_watermark

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("connector.azure")


async def run_azure_sync() -> IngestRunResult:
    """Execute a single sync cycle for Azure Resource Graph."""
    tenant_id = os.getenv("TENANT_ID", "t1")
    sub_id = os.getenv("AZURE_SUBSCRIPTION_ID", "d78af5f4-5d2d-4141-a725-2088437da0ca")
    subscription_ids = [s.strip() for s in sub_id.split(",") if s.strip()]

    pool = await create_db_pool()
    observed_at = datetime.now(timezone.utc)
    started_at = observed_at

    async with pool.acquire() as conn:
        run_id = await start_ingest_run(conn, tenant_id, "azure")
        logger.info("Started Azure ingestion run ID: %s for tenant: %s", run_id, tenant_id)

        result = IngestRunResult(
            tenant_id=tenant_id,
            source_system="azure",
            started_at=started_at,
            status="RUNNING",
        )

        try:
            reader = AzureResourceGraphReader(subscription_ids=subscription_ids)

            logger.info("Querying Azure Resource Graph for NICs...")
            nic_rows = reader.query(NIC_QUERY)
            logger.info("Retrieved %d NICs", len(nic_rows))
            nic_index = build_nic_index(nic_rows)

            logger.info("Querying Azure Resource Graph for Virtual Machines...")
            vm_rows = reader.query(VM_QUERY)
            logger.info("Retrieved %d Virtual Machines", len(vm_rows))

            for vm in vm_rows:
                result.records_read += 1
                record, raw_payload = map_vm_to_normalised_record(
                    vm=vm,
                    nic_index=nic_index,
                    tenant_id=tenant_id,
                    observed_at=observed_at,
                )

                is_new = await upsert_raw_record(
                    conn=conn,
                    tenant_id=tenant_id,
                    source_system="azure",
                    source_id=record.source_id,
                    kind=record.kind,
                    payload=raw_payload,
                    observed_at=observed_at,
                )
                if is_new:
                    result.records_new += 1
                else:
                    logger.debug("Record %s is unchanged (identical hash)", record.source_id)

            result.watermark = format_iso_watermark(observed_at)
            result.status = "SUCCESS"
            logger.info(
                "Completed Azure sync: read=%d, new=%d, errors=%d",
                result.records_read,
                result.records_new,
                result.errors,
            )

        except Exception as exc:
            result.status = "FAILED"
            result.errors += 1
            logger.exception("Azure ingestion failed: %s", exc)

        finally:
            await finish_ingest_run(conn, run_id, result)
            await pool.close()

    return result


def main() -> None:
    """CLI / container entrypoint."""
    result = asyncio.run(run_azure_sync())
    if result.status != "SUCCESS":
        sys.exit(1)


if __name__ == "__main__":
    main()
