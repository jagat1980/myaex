---
name: entity-resolution
description: Build the entity resolver, the temporal graph writer, the pgvector loader and the deterministic risk module.
---
# Entity resolution, graph writer, vectors and risk

## Resolver (`resolver/`)
1. Consume normalised records. Match against `ci_alias` using keys and confidences in
   `docs/ontology.md`, strongest first.
2. Exact/strong match -> reuse canonical `ci_id`. No match -> new `ci_id` (uuid). Ambiguous
   (same hostname, different subscriptions/IPs) -> insert into `er_conflicts`, do NOT merge.
3. Upsert alias rows: (tenant_id, source_system, source_id) -> ci_id, confidence.

## Writer (`writer/`)
1. Idempotent `MERGE` on `uid`; set type label; update `last_seen`, attributes, `confidence`.
2. Relations: MERGE edge with `valid_from`; if a previously-seen edge is absent in a full sync,
   set `valid_to = now()` (never delete).
3. Nightly reconcile job: mark CIs with `last_seen` older than freshness policy as `stale=true`.
4. Batch writes (UNWIND, 500/batch). Write transactions only from this service.

## Vectors (`risk/vectors.py`)
Embed past incidents, RCAs and runbooks for the POC alert type; store with `tenant_id, ci_id,
service, doc_type`; similarity search filtered by tenant.

## Risk (`risk/facts.py`) – deterministic, no LLM
Compute from graph: blast_radius (count of downstream services within max hops), tier1 flag,
active change/freeze, restore point age vs `rpo_hours`, known exploited vuln (BigFix), freshness
and confidence. Map to autonomy tier L0/L1/L2 per signed-off policy; stale data or confidence below
`min_confidence_for_auto` forces L0/L1. 100% unit test coverage for this module.
