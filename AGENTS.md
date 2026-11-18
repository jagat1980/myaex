# Context Graph – Project Rules (always on)

## Mission
Build and deploy a tenant-aware, time-aware **estate context graph** for the BigFix AEX agentic
remediation POC. Scope: ONE tenant, Azure alerts, Windows VMs, NON-PRODUCTION only.
Fill-in values live in `docs/inputs.yaml`. The ontology is in `docs/ontology.md`.

## Stack (do not substitute without asking)
- Kubernetes: AKS or EKS (see inputs.yaml `platform.cloud`), Helm v3, namespace `context-graph`
- Graph: Neo4j **Community Edition** via official chart `neo4j/neo4j`, pinned version
- Relational + vectors: PostgreSQL 16 with `pgvector`
- Language: Python 3.12, `uv` for deps, `pydantic` v2 models, `neo4j` official driver, `httpx`
- MCP server: `fastmcp`, **Streamable HTTP** transport only, path `/mcp`
- Tests: `pytest`; lint: `ruff`; types: `mypy --strict` for `graph/` and `mcp/`
- IaC: Terraform for cloud resources, Helm for in-cluster resources

## Repository layout
```
infra/terraform/   infra/helm/   graph/schema/   connectors/<source>/
resolver/   writer/   risk/   mcp/context_graph/   evals/   docs/
```

## Hard safety rules (NEVER violate)
1. Never target a production cluster, subscription, account or CMDB. Check the kube context
   against `inputs.yaml: platform.allowed_kube_context` before ANY kubectl/helm command; stop if it differs.
2. Never print, log, commit or write secrets to files. Read them only from env vars injected from
   Key Vault / Secrets Manager. `.env` files are gitignored and only hold placeholder names.
3. All source-system connectors are **read-only**. Never call POST/PUT/PATCH/DELETE on ServiceNow,
   SX, SolarWinds, Azure, BigFix, Veeam or Rubrik.
4. Never expose Neo4j, Postgres or the MCP server publicly. Services are ClusterIP; no public
   Ingress or LoadBalancer. Default-deny NetworkPolicy in the namespace.
5. The MCP server must NEVER execute Cypher supplied by a caller or an LLM. Only fixed,
   parameterised queries. Use read transactions only (`execute_read`).
6. `tenant_id` in the MCP server comes from the authenticated token, never from tool arguments.
7. Ask before: deleting any resource, running `helm uninstall`, dropping data, or changing schema
   constraints.

## Data model invariants
- Every infrastructure node has label `:CI` plus a type label, e.g. `(:CI:VM)`.
- Unique key: `uid = "<tenant_id>:<ci_id>"` (Community Edition has no NODE KEY constraints).
- Every node and edge carries: `tenant_id, source_system, source_id, valid_from, valid_to,
  last_seen, confidence`.
- Never hard-delete history: close edges by setting `valid_to`.
- All writes are idempotent `MERGE` upserts; re-running a load must not create duplicates.

## Engineering standards
- Each connector: pull (incremental) -> store raw in `raw_records` -> publish normalised record ->
  record run in `ingest_runs`. Retries with backoff; respect API rate limits.
- Structured JSON logs; OpenTelemetry spans for every external call and every MCP tool call.
- Every module ships with unit tests; integration tests run against the non-prod cluster.
- MCP tool responses: compact JSON, < 4k tokens, include `source_system` and `last_seen` per fact.

## Working style
- Use Planning mode: produce an implementation plan artifact per stage and wait for approval.
- Work stage by stage from `docs/STAGES.md`; finish a stage's "Done when" checks before moving on.
- If an input in `docs/inputs.yaml` is missing or `TODO`, stop and ask; do not guess endpoints,
  IDs or credentials.
