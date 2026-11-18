# Build stages (run in order; one plan artifact + approval per stage)

| Stage | Skill to use | Done when |
|---|---|---|
| 1 Infra | deploy-neo4j | Neo4j pod Ready, schema applied, smoke test passes, NetworkPolicy default-deny, Postgres tables exist |
| 2 Connectors | build-connector (x5: itsm, solarwinds, azure, bigfix, backup) | Each loads POC tenant into raw_records; ingest_runs shows success; re-run creates 0 duplicates |
| 3 Resolution + writer | entity-resolution | >=95% of POC VMs resolve to one CI with confidence >=0.9; conflicts queued; graph populated |
| 4 Vectors + risk | entity-resolution (risk section) | pgvector loaded with incidents/RCAs/runbooks; risk module unit tests pass |
| 5 MCP server | context-graph-mcp | 6 tools pass tests; p95 < 1s; 401 without token; cross-tenant returns nothing |
| 6 Validation | validate-graph | Validation report artifact meets all pass criteria |
| 7 AEX registration | MANUAL (human) | Endpoint added in AEX Gateway; tool visible in Tool Library; tested in Play |
