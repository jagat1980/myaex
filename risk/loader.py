"""Seed dataset and loader for past incidents, RCAs, and runbooks in pgvector."""

import logging
from typing import Any
import uuid
import asyncpg
from risk.models import VectorDocument
from risk.vectors import VectorStore

logger = logging.getLogger("risk.loader")

# Canonical CI ID for POC Windows VM mypcpoc
MYPCPOC_CI_ID = uuid.UUID("46e8ff7b-80fb-493d-a3c4-613feafb4177")

SEED_DOCUMENTS: list[dict[str, Any]] = [
    # 1. Incidents
    {
        "doc_id": "INC-1001",
        "doc_type": "incident",
        "title": "C: Drive 98% full on Windows VM mypcpoc due to CBS and DISM component accumulation",
        "content": (
            "Alert triggered: Disk Space Critical on host mypcpoc. Volume C: has less than 2% free space remaining. "
            "System drive space exhausted by rapid growth in C:\\Windows\\Logs\\CBS and corrupted Windows component "
            "store temp files. Operating system responsiveness degraded; patching blocked."
        ),
        "service_name": "CoreInfrastructure",
        "ci_id": MYPCPOC_CI_ID,
        "metadata": {"severity": "P1", "affected_os": "Windows Server 2019", "alert_type": "DiskSpace"},
    },
    {
        "doc_id": "INC-1002",
        "doc_type": "incident",
        "title": "Windows Update Service (wuauserv) hung at 100% CPU on Windows Server host",
        "content": (
            "CPU utilization exceeded 95% on mypcpoc for over 30 minutes. Task manager reveals svchost.exe hosting "
            "wuauserv (Windows Update) consuming 100% of core CPU capacity. High memory allocation detected. "
            "Automated health check failed."
        ),
        "service_name": "CoreInfrastructure",
        "ci_id": MYPCPOC_CI_ID,
        "metadata": {"severity": "P2", "affected_os": "Windows Server 2019", "alert_type": "HighCPU"},
    },
    {
        "doc_id": "INC-1003",
        "doc_type": "incident",
        "title": "IIS W3SVC World Wide Web Publishing Service terminated unexpectedly after patch rollout",
        "content": (
            "HTTP 503 Service Unavailable alert on web server endpoint. Investigation shows W3SVC service in "
            "stopped state following cumulative update installation. Worker process failed to bind to TCP port 80."
        ),
        "service_name": "WebFrontend",
        "ci_id": None,
        "metadata": {"severity": "P1", "affected_os": "Windows Server 2022", "alert_type": "ServiceDown"},
    },
    {
        "doc_id": "INC-1004",
        "doc_type": "incident",
        "title": "High memory exhaustion caused by orphaned worker threads on application node",
        "content": (
            "RAM utilization reached 96% on backend node. SolarWinds telemetry reported paging rate spike and "
            "slow transaction response times. Java runtime garbage collection overhead limit exceeded."
        ),
        "service_name": "AppProcessing",
        "ci_id": None,
        "metadata": {"severity": "P2", "affected_os": "Linux", "alert_type": "MemoryExhaustion"},
    },

    # 2. Root Cause Analyses (RCAs)
    {
        "doc_id": "RCA-2001",
        "doc_type": "rca",
        "title": "RCA: Uncompressed CBS log archives in C:\\Windows\\Logs\\CBS caused disk space exhaustion",
        "content": (
            "Root Cause Analysis: Component-Based Servicing (CBS) logs failed to compress automatically into Cab_*.log "
            "due to disk corruption in temp storage. As a result, uncompressed text logs accumulated up to 45 GB. "
            "Corrective action: Executed Dism.exe /Online /Cleanup-Image /StartComponentCleanup /ResetBase and purged "
            "stale CBS logs older than 7 days. Scheduled cleanup task restored."
        ),
        "service_name": "CoreInfrastructure",
        "ci_id": MYPCPOC_CI_ID,
        "metadata": {"root_cause_category": "DiskAccumulation", "resolved_by": "BigFix", "rca_id": "RCA-2001"},
    },
    {
        "doc_id": "RCA-2002",
        "doc_type": "rca",
        "title": "RCA: Deadlock in telemetry agent thread caused persistent 100% CPU on VM cores",
        "content": (
            "Root Cause Analysis: Telemetry monitoring agent entered an infinite spinlock when parsing corrupted "
            "Windows Event Log security channels. Action: Terminated agent PID, applied hotfix patch, and cleared "
            "corrupted event log records."
        ),
        "service_name": "CoreInfrastructure",
        "ci_id": MYPCPOC_CI_ID,
        "metadata": {"root_cause_category": "SoftwareDeadlock", "rca_id": "RCA-2002"},
    },
    {
        "doc_id": "RCA-2003",
        "doc_type": "rca",
        "title": "RCA: IIS AppPool recycling misconfiguration caused application memory leak",
        "content": (
            "Root Cause Analysis: IIS Application Pool private memory limit was set to unlimited, allowing orphaned "
            "sessions to leak unmanaged memory. Action: Reconfigured periodic recycling every 1740 minutes and 4GB ceiling."
        ),
        "service_name": "WebFrontend",
        "ci_id": None,
        "metadata": {"root_cause_category": "ConfigurationError", "rca_id": "RCA-2003"},
    },
    {
        "doc_id": "RCA-2004",
        "doc_type": "rca",
        "title": "RCA: Missing filesystem expansion following Azure OS disk resize in portal",
        "content": (
            "Root Cause Analysis: Disk volume was resized from 127 GB to 256 GB in Azure portal, but the guest OS "
            "partition was not extended. Disk remained full from guest perspective. Action: Executed PowerShell "
            "Resize-Partition."
        ),
        "service_name": "StorageOps",
        "ci_id": None,
        "metadata": {"root_cause_category": "StorageProvisioning", "rca_id": "RCA-2004"},
    },

    # 3. Runbooks
    {
        "doc_id": "RB-3001",
        "doc_type": "runbook",
        "title": "Runbook: Safe Windows OS Disk Cleanup - CBS logs, SoftwareDistribution, DISM ResetBase",
        "content": (
            "Remediation Runbook for Windows Server Disk Space Exhaustion:\n"
            "Step 1: Stop Windows Update service (net stop wuauserv).\n"
            "Step 2: Delete files in C:\\Windows\\SoftwareDistribution\\Download older than 14 days.\n"
            "Step 3: Clean C:\\Windows\\Logs\\CBS archive logs (.log files except the active Cbs.log).\n"
            "Step 4: Execute: Dism.exe /online /Cleanup-Image /StartComponentCleanup /ResetBase.\n"
            "Step 5: Purge C:\\Windows\\Temp and user temporary caches.\n"
            "Step 6: Start Windows Update service (net start wuauserv) and verify at least 15% free space."
        ),
        "service_name": "CoreInfrastructure",
        "ci_id": MYPCPOC_CI_ID,
        "metadata": {"automation_eligible": True, "target_os": "Windows", "risk_level": "Low", "runbook_id": "RB-3001"},
    },
    {
        "doc_id": "RB-3002",
        "doc_type": "runbook",
        "title": "Runbook: Restart Windows Service with Pre/Post Health Checks and Rollback verification",
        "content": (
            "Remediation Runbook for Hung Windows Service:\n"
            "Step 1: Verify service status via sc.exe query <ServiceName>.\n"
            "Step 2: If State is STOP_PENDING or START_PENDING, capture PID and terminate via taskkill /F /PID.\n"
            "Step 3: Execute sc.exe start <ServiceName>.\n"
            "Step 4: Wait 15 seconds and verify status is RUNNING.\n"
            "Step 5: Verify listening port bindings and event log entries."
        ),
        "service_name": "CoreInfrastructure",
        "ci_id": None,
        "metadata": {"automation_eligible": True, "target_os": "Windows", "risk_level": "Low", "runbook_id": "RB-3002"},
    },
    {
        "doc_id": "RB-3003",
        "doc_type": "runbook",
        "title": "Runbook: Azure Virtual Machine OS Disk Resize via CLI and filesystem expansion",
        "content": (
            "Remediation Runbook for Expanding Azure VM OS Disk:\n"
            "Step 1: Stop VM: az vm deallocate -g <RG> -n <VM>.\n"
            "Step 2: Update disk: az disk update -g <RG> -n <DiskName> --size-gb <NewSize>.\n"
            "Step 3: Start VM: az vm start -g <RG> -n <VM>.\n"
            "Step 4: In guest OS PowerShell: Update-Disk -Number 0; Resize-Partition -DriveLetter C -Size (Get-PartitionSupportedSize -DriveLetter C).SizeMax."
        ),
        "service_name": "StorageOps",
        "ci_id": None,
        "metadata": {"automation_eligible": False, "target_os": "Windows", "risk_level": "Medium", "runbook_id": "RB-3003"},
    },
    {
        "doc_id": "RB-3004",
        "doc_type": "runbook",
        "title": "Runbook: Windows Memory Dump capture and IIS AppPool automated recycling",
        "content": (
            "Remediation Runbook for Memory Leaks:\n"
            "Step 1: Capture mini-dump using procdump.exe -ma <PID> C:\\Dumps\\.\n"
            "Step 2: Recycle AppPool: %SystemRoot%\\System32\\inetsrv\\appcmd.exe recycle apppool /apppool.name:<AppPoolName>.\n"
            "Step 3: Verify worker process w3wp.exe initializes with baseline memory footprint (< 500MB)."
        ),
        "service_name": "WebFrontend",
        "ci_id": None,
        "metadata": {"automation_eligible": True, "target_os": "Windows", "risk_level": "Medium", "runbook_id": "RB-3004"},
    },
]


async def load_seed_documents(conn: asyncpg.Connection, tenant_id: str = "t1") -> int:
    """Load the seed intelligence dataset into PostgreSQL pgvector embeddings table."""
    store = VectorStore(conn)
    loaded_count = 0

    for item in SEED_DOCUMENTS:
        doc = VectorDocument(
            tenant_id=tenant_id,
            doc_id=item["doc_id"],
            doc_type=item["doc_type"],
            title=item["title"],
            content=item["content"],
            service_name=item.get("service_name"),
            ci_id=item.get("ci_id"),
            metadata=item.get("metadata", {}),
        )
        row_id = await store.upsert_document(doc)
        loaded_count += 1
        logger.info("Loaded vector document %s (id: %d, type: %s)", doc.doc_id, row_id, doc.doc_type)

    logger.info("Successfully loaded %d seed documents into pgvector for tenant %s", loaded_count, tenant_id)
    return loaded_count
