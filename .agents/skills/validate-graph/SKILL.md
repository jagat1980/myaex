---
name: validate-graph
description: Validate the context graph end to end and produce a go/no-go report artifact.
---
# Validation
Run and report (table: check, result, evidence):
1. Accuracy: compare `evals/sample_cis.csv` (50 hand-verified CIs) to `get_ci_context`; pass >= 95%.
2. Freshness: max(last_seen) per source within policy.
3. Performance: p95 tool latency < 1s, blast_radius < 2s (100 calls each).
4. Isolation: token for tenant A cannot read tenant B (seed synthetic tenant B).
5. Resilience: stop one connector; data marked stale, MCP still serves.
6. Security: no-token 401; Cypher/JSON injection strings in args rejected or inert; no public
   endpoints (`kubectl get svc,ingress -A` check).
7. Replay: for 20 past incidents, show the graph context returned; flag where root-cause CI missing.
Output `docs/VALIDATION_REPORT.md` and a go/no-go recommendation. Do not mark go if any check fails.
