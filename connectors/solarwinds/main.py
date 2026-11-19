"""SolarWinds Observability SaaS connector entrypoint."""

import asyncio
from datetime import datetime, timezone
import logging
import os
import sys
from connectors.common.db import (
    create_db_pool,
    upsert_raw_record,
    start_ingest_run,
    finish_ingest_run,
)
from connectors.common.models import IngestRunResult
from connectors.common.watermark import format_iso_watermark
from connectors.solarwinds.client import SolarWindsSaaSClient
from connectors.solarwinds.extract import extract_solarwinds_host

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("connector.solarwinds")


def get_solarwinds_token() -> str:
    """Retrieve SolarWinds API token from environment or Key Vault CSI volume mount."""
    token = os.getenv("SOLARWINDS_API_TOKEN")
    token_file = os.getenv("SOLARWINDS_TOKEN_FILE", "/mnt/secrets-store/solarwinds-credentials")

    if not token and os.path.exists(token_file):
        try:
            with open(token_file, "r", encoding="utf-8") as f:
                token = f.read().strip()
        except Exception:
            pass

    return token or ""


async def run_solarwinds_sync() -> IngestRunResult:
    """Execute a single sync cycle for SolarWinds Observability SaaS."""
    tenant_id = os.getenv("TENANT_ID", "t1")
    api_url = os.getenv("SOLARWINDS_API_URL", "https://api.eu-01.cloud.solarwinds.com")
    api_token = get_solarwinds_token()

    pool = await create_db_pool()
    observed_at = datetime.now(timezone.utc)
    started_at = observed_at

    async with pool.acquire() as conn:
        run_id = await start_ingest_run(conn, tenant_id, "solarwinds")
        logger.info("Started SolarWinds SaaS ingestion run ID: %s for tenant: %s", run_id, tenant_id)

        result = IngestRunResult(
            tenant_id=tenant_id,
            source_system="solarwinds",
            started_at=started_at,
            status="RUNNING",
        )

        try:
            async with SolarWindsSaaSClient(base_url=api_url, api_token=api_token) as client:
                logger.info("Listing host entities from SolarWinds Observability SaaS (%s)...", api_url)
                entities = await client.list_entities(entity_type="host")
                logger.info("Retrieved %d host entities from SolarWinds", len(entities))

                for entity in entities:
                    result.records_read += 1
                    record, raw_payload = extract_solarwinds_host(
                        entity=entity,
                        tenant_id=tenant_id,
                        observed_at=observed_at,
                    )

                    is_new = await upsert_raw_record(
                        conn=conn,
                        tenant_id=tenant_id,
                        source_system="solarwinds",
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
                "Completed SolarWinds sync: read=%d, new=%d, errors=%d",
                result.records_read,
                result.records_new,
                result.errors,
            )

        except Exception as exc:
            result.status = "FAILED"
            result.errors += 1
            logger.exception("SolarWinds ingestion failed: %s", exc)

        finally:
            await finish_ingest_run(conn, run_id, result)

    await pool.close()
    return result


def main() -> None:
    """CLI / container entrypoint."""
    result = asyncio.run(run_solarwinds_sync())
    if result.status != "SUCCESS":
        sys.exit(1)


if __name__ == "__main__":
    main()
