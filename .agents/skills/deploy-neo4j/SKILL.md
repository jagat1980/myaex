---
name: deploy-neo4j
description: Deploy Neo4j Community and Postgres+pgvector infrastructure for the context graph on the NON-PROD AKS/EKS cluster and apply the graph schema.
---
# Deploy Neo4j and data stores

1. Read `docs/inputs.yaml`. Stop if any `platform`, `neo4j` or `postgres` field is TODO.
2. Verify `kubectl config current-context` == `platform.allowed_kube_context`. Stop if not.
3. Generate `infra/helm/neo4j/values.yaml`:
   - `neo4j.name: context-graph`, `neo4j.edition: community`, `neo4j.passwordFromSecret: neo4j-auth`
   - resources from inputs; heap + pagecache + 1Gi must be < container memory
   - dynamic PVC with `platform.storage_class` and `neo4j.disk`
   - service type ClusterIP; enable `db.logs.query.enabled: INFO`
   - Validate keys against `helm show values neo4j/neo4j --version <pinned>` before installing.
4. Create namespace, default-deny NetworkPolicy, and allow-policies:
   Bolt 7687 only from pods labelled `app in (graph-writer, context-graph-mcp)`.
5. Create the `neo4j-auth` secret via the secret-store CSI driver (SecretProviderClass). Never echo the value.
6. `helm repo add neo4j https://helm.neo4j.com/neo4j && helm repo update`, then
   `helm upgrade --install context-graph neo4j/neo4j -n context-graph -f values.yaml --version <pinned>`.
   Show the command and wait for approval before running.
7. Wait for rollout; then apply `graph/schema/001_constraints.cypher`:
   uniqueness on `:CI(uid)`, `:BusinessService(uid)`, `:AssignmentGroup(uid)`, `:Change(uid)`,
   `:Incident(uid)`, `:BackupJob(uid)`; indexes on `:CI(tenant_id)`, `:CI(name)`, `:CI(ip)`, `:CI(last_seen)`.
8. Postgres: Terraform module (or existing server) + migration `001_init.sql`:
   `CREATE EXTENSION vector;` tables `raw_records`, `ingest_runs`, `ci_alias`, `er_conflicts`,
   `embeddings(vector(768))`, `audit_log` (append-only: revoke UPDATE/DELETE).
9. Backups: VolumeSnapshotClass + nightly CronJob snapshot of the Neo4j PVC; document
   "rebuild from sources" as the DR procedure in `docs/RUNBOOK.md`.
10. Smoke test with a synthetic tenant `t-smoke`, then delete only `t-smoke` data.
Output an artifact summarising resources created and test results.
