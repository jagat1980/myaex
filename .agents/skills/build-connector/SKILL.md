---
name: build-connector
description: Build one read-only source connector (itsm, solarwinds, azure, bigfix or backup) that loads the POC tenant into the raw store.
---
# Build a source connector

Inputs: connector name, matching block in `docs/inputs.yaml`.

1. Create `connectors/<name>/` with `client.py`, `models.py` (pydantic), `extract.py`, `main.py`, tests.
2. Client rules: httpx with timeouts, retry with exponential backoff on 429/5xx, pagination,
   **GET only** (assert in code that no other method is used). Credentials from env vars only.
3. Incremental pull using a watermark stored in `ingest_runs` (e.g. `sys_updated_on`, `lastModified`).
4. Normalise each record to `NormalisedRecord`:
   `tenant_id, source_system, source_id, kind, name, fqdn, ip, cloud_id, attributes{}, relations[], observed_at`.
5. Persist raw JSON to `raw_records` (upsert on source_system+source_id+hash), then publish
   normalised records to the resolver (Postgres queue table or Service Bus/SQS per inputs).
6. Write an `ingest_runs` row: start/end, counts (read/new/changed/errors), watermark.
7. Package as container; deploy as Kubernetes CronJob using `poll_minutes`; ServiceAccount with
   workload identity where the cloud supports it.
8. Tests: unit tests with recorded fixtures (no live calls); one integration test against non-prod
   that loads <= 100 records.
Source specifics:
- itsm: tables listed in inputs; map cmdb_rel_ci to relations; changes and incidents as nodes.
- solarwinds: entities and dependency/topology edges.
- azure: Resource Graph KQL for VMs, disks, NICs, VNets, SQL; include resource id + tags.
- bigfix: computers + properties (OS, patch compliance, last report time) via REST/session relevance.
- backup: jobs, protected objects, last success time, restore points.
