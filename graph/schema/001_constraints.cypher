// ==============================================================================
// Context Graph – Neo4j Community Schema Constraints & Indexes
// Stage 1: Constraints and Performance Indexes
// Invariant: Unique composite keys use uid = "<tenant_id>:<ci_id>"
// (Community Edition does not support multi-property NODE KEY constraints)
// ==============================================================================

// Uniqueness Constraints
CREATE CONSTRAINT ci_uid_unique IF NOT EXISTS
FOR (c:CI) REQUIRE c.uid IS UNIQUE;

CREATE CONSTRAINT business_service_uid_unique IF NOT EXISTS
FOR (s:BusinessService) REQUIRE s.uid IS UNIQUE;

CREATE CONSTRAINT assignment_group_uid_unique IF NOT EXISTS
FOR (g:AssignmentGroup) REQUIRE g.uid IS UNIQUE;

CREATE CONSTRAINT change_uid_unique IF NOT EXISTS
FOR (ch:Change) REQUIRE ch.uid IS UNIQUE;

CREATE CONSTRAINT incident_uid_unique IF NOT EXISTS
FOR (i:Incident) REQUIRE i.uid IS UNIQUE;

CREATE CONSTRAINT backup_job_uid_unique IF NOT EXISTS
FOR (b:BackupJob) REQUIRE b.uid IS UNIQUE;

// Performance Indexes for Fast Lookups and Ingestion Filtering
CREATE INDEX ci_tenant_id_idx IF NOT EXISTS
FOR (c:CI) ON (c.tenant_id);

CREATE INDEX ci_name_idx IF NOT EXISTS
FOR (c:CI) ON (c.name);

CREATE INDEX ci_ip_idx IF NOT EXISTS
FOR (c:CI) ON (c.ip);

CREATE INDEX ci_last_seen_idx IF NOT EXISTS
FOR (c:CI) ON (c.last_seen);
