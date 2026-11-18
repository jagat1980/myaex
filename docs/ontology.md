# POC Ontology
## Node labels
Tenant, BusinessService, Application, AssignmentGroup,
CI:VM, CI:Host, CI:Database, CI:NetworkDevice, CI:CloudResource,
BackupJob, RestorePoint, Incident, Change, Runbook, RCA

## Relationships
(:CI)-[:RUNS_ON]->(:CI)              VM -> Host / cloud resource
(:CI)-[:DEPENDS_ON]->(:CI)           app/db dependency
(:CI)-[:SUPPORTS]->(:BusinessService)
(:CI)-[:CONNECTS_TO]->(:CI:NetworkDevice)
(:CI)-[:PROTECTED_BY]->(:BackupJob)
(:BackupJob)-[:HAS_RESTORE_POINT]->(:RestorePoint)
(:CI|BusinessService)-[:OWNED_BY]->(:AssignmentGroup)
(:Incident)-[:RAISED_ON]->(:CI)
(:CI)-[:CHANGED_BY]->(:Change)
(:Incident)-[:CAUSED_BY]->(:CI)
(:Incident)-[:RESOLVED_BY]->(:RCA)

## Field ownership (source of truth)
| Field | Source |
|---|---|
| ci_id, business service, owner, tier | ITSM CMDB |
| topology, dependencies | SolarWinds |
| cloud resource id, tags, size | Azure Resource Graph |
| OS, patch state, last report | BigFix |
| backup jobs, restore points | Veeam / Rubrik |
| changes, incidents | ITSM |

## Entity resolution match keys (strongest first)
1. Azure resource ID / vCenter UUID (confidence 1.0)
2. CMDB sys_id referenced by another source (0.95)
3. FQDN (0.9)
4. hostname + IP (0.8)
5. hostname only (0.6) -> conflicts go to review queue
