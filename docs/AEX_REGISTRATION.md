# BigFix AEX Gateway – Context Graph MCP Server Registration Guide

This document provides the exact configuration details required to register the read-only **Context Graph MCP Server** in the BigFix AEX Gateway and Tool Library for Stage 7 registration.

---

## 1. Connection & Endpoint Details

| Parameter | Configuration Value | Notes |
|---|---|---|
| **Service Name** | `context-graph-mcp` | Internal Kubernetes Service |
| **Transport** | `Streamable HTTP` | Standard FastMCP Streamable HTTP |
| **Endpoint URL** | `http://context-graph-mcp.context-graph.svc.cluster.local:3001/mcp` | In-cluster ClusterIP endpoint |
| **Health Probe URL** | `http://context-graph-mcp.context-graph.svc.cluster.local:3001/healthz` | For AEX MCP Health Monitor |
| **Port** | `3001` | TCP, ClusterIP (No public IP / Hard Safety Rule 4) |
| **Authentication Scheme** | `Bearer Token` | `Authorization: Bearer <TOKEN>` |
| **Token Secret Location** | Azure Key Vault: `kv-cg-nonprod-hf3i3` / `mcp-auth-token` | Injected into CSI volume in AKS |
| **Tenant Context** | `t1` (POC-Tenant) | Derived strictly from token (Hard Safety Rule 6) |

---

## 2. Authentication Configuration

The Context Graph MCP server strictly enforces **Hard Safety Rule 6**: the `tenant_id` is derived from the authenticated Bearer token and is never accepted as a tool argument.

In the AEX Gateway HTTP headers configuration, specify:
```http
Authorization: Bearer <mcp-auth-token>
```
> [!NOTE]
> Requests missing this header or providing an invalid token will receive `HTTP 401 Unauthorized` without invoking any tool handler.

---

## 3. Registered Tools Library (6 Tools)

### Tool 1: `get_ci_context`
- **Description**: Retrieve Configuration Item metadata, environment tier, supporting business service, operational ownership group, confidence score, and staleness indicator. Call during initial incident triage to determine CI properties and business impact.
- **Parameters**:
  - `ci` (string, required): Configuration Item identifier (canonical UUID or hostname, e.g. `mypcpoc`).
- **Sample Request**:
  ```json
  {
    "ci": "mypcpoc"
  }
  ```
- **Sample Response**:
  ```json
  {
    "found": true,
    "ci_id": "t1:46e8ff7b-80fb-493d-a3c4-613feafb4177",
    "name": "mypcpoc",
    "type": { "value": "VM", "source_system": "azure", "last_seen": "2026-11-20T10:00:00Z" },
    "env": { "value": "non-production", "source_system": "azure", "last_seen": "2026-11-20T10:00:00Z" },
    "tier": { "value": "Tier-2", "source_system": "azure", "last_seen": "2026-11-20T10:00:00Z" },
    "confidence": { "value": 1.0, "source_system": "azure", "last_seen": "2026-11-20T10:00:00Z" },
    "is_stale": { "value": false, "source_system": "azure", "last_seen": "2026-11-20T10:00:00Z" },
    "business_service": { "name": "POC-Portal", "tier": "Tier-2", "source_system": "itsm", "last_seen": "2026-11-20T10:00:00Z" },
    "owner": { "group": "CloudOps-Windows", "source_system": "itsm", "last_seen": "2026-11-20T10:00:00Z" }
  }
  ```

---

### Tool 2: `blast_radius`
- **Description**: Evaluate downstream blast radius up to 3 graph hops for a Configuration Item. Traces downstream dependency and network connectivity paths, enumerating affected CIs and business services. Call before executing any disruptive remediation action.
- **Parameters**:
  - `ci` (string, required): Configuration Item identifier.
  - `hops` (integer, optional, default: 2, range: 1–3): Traversal depth.
- **Sample Request**:
  ```json
  {
    "ci": "mypcpoc",
    "hops": 2
  }
  ```
- **Sample Response**:
  ```json
  {
    "root_ci": "mypcpoc",
    "hops_evaluated": 2,
    "downstream_ci_count": 2,
    "downstream_service_count": 1,
    "affected_services": ["POC-Portal"],
    "is_blast_radius_safe": true,
    "downstream_cis": [
      {
        "ci_id": "t1:nic-237",
        "name": "mypcpoc237_z1",
        "type": "NetworkDevice",
        "tier": "Standard",
        "distance_hops": 1,
        "source_system": "azure",
        "last_seen": "2026-11-20T10:00:00Z"
      }
    ]
  }
  ```

---

### Tool 3: `recent_changes`
- **Description**: Retrieve recent change requests, maintenance windows, active change freezes, and concurrent incidents on a target Configuration Item and its 1-hop infrastructure neighbors within lookback window.
- **Parameters**:
  - `ci` (string, required): Configuration Item identifier.
  - `hours` (integer, optional, default: 24, range: 1–168): Lookback window.
- **Sample Request**:
  ```json
  {
    "ci": "mypcpoc",
    "hours": 24
  }
  ```
- **Sample Response**:
  ```json
  {
    "root_ci": "mypcpoc",
    "hours_window": 24,
    "has_active_change": false,
    "has_active_freeze": false,
    "direct_changes_count": 0,
    "direct_incidents_count": 0,
    "neighbor_changes_count": 0,
    "direct_changes": [],
    "direct_incidents": [],
    "neighbor_changes": []
  }
  ```

---

### Tool 4: `backup_status`
- **Description**: Check backup health, last restore point timestamp, and Recovery Point Objective (RPO) compliance (threshold <= 24 hours) for a Configuration Item. Call before high-risk changes.
- **Parameters**:
  - `ci` (string, required): Configuration Item identifier.
- **Sample Request**:
  ```json
  {
    "ci": "mypcpoc"
  }
  ```
- **Sample Response**:
  ```json
  {
    "root_ci": "mypcpoc",
    "backup_found": true,
    "backup_healthy": true,
    "within_rpo": true,
    "rpo_threshold_hours": 24.0,
    "restore_point_age_hours": 3.5,
    "last_backup_job": "AzureBackup-Default",
    "last_backup_success": "2026-11-20T06:30:00Z",
    "source_system": "azure",
    "last_seen": "2026-11-20T10:00:00Z"
  }
  ```

---

### Tool 5: `similar_incidents`
- **Description**: Perform semantic vector search using PostgreSQL pgvector to retrieve relevant historical incidents, root cause analyses (RCAs), and remediation runbooks. Call when diagnosing an alert or symptom.
- **Parameters**:
  - `text` (string, required, 3–500 chars): Symptom description, log message, or alert text.
  - `ci` (string, optional): Local CI identifier for correlated context.
  - `k` (integer, optional, default: 3, range: 1–5): Number of matches.
- **Sample Request**:
  ```json
  {
    "text": "Windows C drive disk space 100% full CBS log cleanup",
    "ci": "mypcpoc",
    "k": 2
  }
  ```
- **Sample Response**:
  ```json
  {
    "query": "Windows C drive disk space 100% full CBS log cleanup",
    "ci_context": "mypcpoc",
    "k_requested": 2,
    "results_count": 2,
    "results": [
      {
        "doc_id": "INC-1001",
        "doc_type": "incident",
        "title": "C: Drive 98% full on Windows VM mypcpoc due to CBS and DISM component accumulation",
        "similarity": 0.4308,
        "content_excerpt": "C: drive reached 98% disk capacity on Windows VM mypcpoc. Investigation revealed CBS log accumulation in C:\\Windows\\Logs\\CBS and corrupted component store.",
        "source_system": "itsm",
        "last_seen": "2026-11-20T10:00:00Z"
      },
      {
        "doc_id": "RB-3001",
        "doc_type": "runbook",
        "title": "Runbook: Safe Windows OS Disk Cleanup - CBS logs, SoftwareDistribution, DISM ResetBase",
        "similarity": 0.2937,
        "content_excerpt": "1. Run DISM.exe /online /Cleanup-Image /StartComponentCleanup /ResetBase. 2. Stop wuauserv, purge SoftwareDistribution. 3. Delete *.log in C:\\Windows\\Logs\\CBS.",
        "source_system": "runbook",
        "last_seen": "2026-11-20T10:00:00Z"
      }
    ]
  }
  ```

---

### Tool 6: `owner_and_route`
- **Description**: Resolve operational ownership, primary assignment group, escalation channel/on-call path, and permitted automation execution engines (e.g. BigFix) for a Configuration Item.
- **Parameters**:
  - `ci` (string, required): Configuration Item identifier.
- **Sample Request**:
  ```json
  {
    "ci": "mypcpoc"
  }
  ```
- **Sample Response**:
  ```json
  {
    "root_ci": "mypcpoc",
    "ci_name": "mypcpoc",
    "assignment_group": "CloudOps-Windows",
    "escalation_channel": "pagerduty://cloudops-oncall",
    "permitted_executor": "BigFix",
    "auto_remediation_permitted": true,
    "source_system": "itsm",
    "last_seen": "2026-11-20T10:00:00Z"
  }
  ```

---

## 4. Verification & Testing

To test connection health from within the cluster:
```bash
# 1. Health probe check
curl -s http://context-graph-mcp.context-graph.svc.cluster.local:3001/healthz

# 2. Unauthenticated check (must return 401)
curl -s -X POST http://context-graph-mcp.context-graph.svc.cluster.local:3001/mcp

# 3. Authenticated tool execution
curl -s -X POST http://context-graph-mcp.context-graph.svc.cluster.local:3001/mcp \
  -H "Authorization: Bearer <mcp-auth-token>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
```
