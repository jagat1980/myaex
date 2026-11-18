---
name: context-graph-mcp
description: Build, harden and deploy the read-only Context Graph MCP server (FastMCP, Streamable HTTP).
---
# Context Graph MCP server (`mcp/context_graph/`)

Tools (each = one fixed parameterised Cypher/SQL query, read transaction, LIMIT + timeout):
| Tool | Args | Returns |
|---|---|---|
| get_ci_context | ci (name or ci_id) | CI, type, env, service, tier, owner, last_seen, confidence |
| blast_radius | ci, hops<=3 | downstream CIs and services (max 200) |
| recent_changes | ci, hours<=168 | changes/incidents on CI and 1-hop neighbours |
| backup_status | ci | last success, restore point age, within_rpo |
| similar_incidents | text, ci? , k<=5 | top-k incidents/RCAs from pgvector |
| owner_and_route | ci | assignment group, escalation, permitted executor |

Requirements:
1. Streamable HTTP on `/mcp`, port from inputs. Bearer token auth; token maps to `tenant_id`
   (never accept tenant as an argument). Missing/invalid token -> 401.
2. Validate all args with pydantic (lengths, allowed chars, numeric bounds).
3. Responses: compact JSON < 4k tokens, each fact with `source_system` and `last_seen`.
4. Tool descriptions written for an LLM: what it returns and when to use it.
5. Audit every call to `audit_log` (caller, tool, args hash, result count, latency).
6. OpenTelemetry spans; `/healthz` endpoint for the AEX MCP Health Monitor.
7. Deploy: Deployment (2 replicas), ClusterIP Service, internal TLS (cert-manager), NetworkPolicy
   allowing ingress only from the AEX Gateway host CIDR in inputs.
8. Tests: per-tool unit tests on a fixture graph; injection tests (Cypher in args has no effect);
   cross-tenant test returns empty; load test p95 < 1s.
9. Write `docs/AEX_REGISTRATION.md`: endpoint URL, transport, auth header, tool list – for the human
   who registers it in the AEX Gateway.
