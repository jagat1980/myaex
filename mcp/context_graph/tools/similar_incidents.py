"""Tool: similar_incidents

Performs semantic vector similarity search using PostgreSQL pgvector (<=> cosine distance)
to retrieve relevant historical incidents, root cause analyses (RCAs), and remediation runbooks.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import asyncpg
from risk.vectors import format_pgvector, generate_embedding

logger = logging.getLogger(__name__)

SQL_SIMILAR_DOCUMENTS = """
SELECT id, doc_id, doc_type, title, content, metadata,
       1.0 - (embedding <=> $1::vector) AS similarity,
       created_at
FROM embeddings
WHERE tenant_id = $2
ORDER BY embedding <=> $1::vector
LIMIT $3;
"""


async def execute_similar_incidents(
    pool: asyncpg.Pool,
    tenant_id: str,
    text: str,
    ci: Optional[str] = None,
    k: int = 3,
) -> Dict[str, Any]:
    """Execute semantic vector search against PostgreSQL embeddings table."""
    bounded_k = max(1, min(5, k))
    
    # Enrich query with CI context if provided
    query_text = f"{ci} {text}" if ci else text
    query_embedding = generate_embedding(query_text)
    pgvector_str = format_pgvector(query_embedding)

    async with pool.acquire() as conn:
        rows = await conn.fetch(SQL_SIMILAR_DOCUMENTS, pgvector_str, tenant_id, bounded_k)

    results: List[Dict[str, Any]] = []
    for r in rows:
        created_str = r["created_at"].isoformat() if r["created_at"] else datetime.now(timezone.utc).isoformat()
        metadata = json.loads(r["metadata"]) if isinstance(r["metadata"], str) else (r["metadata"] or {})
        source_sys = metadata.get("source_system", "itsm" if r["doc_type"] == "incident" else "runbook")

        results.append({
            "doc_id": r["doc_id"],
            "doc_type": r["doc_type"],
            "title": r["title"],
            "similarity": round(float(r["similarity"]), 4),
            "content_excerpt": r["content"][:280] + ("..." if len(r["content"]) > 280 else ""),
            "metadata": metadata,
            "source_system": source_sys,
            "last_seen": created_str,
        })

    return {
        "query": text,
        "ci_context": ci,
        "k_requested": bounded_k,
        "results_count": len(results),
        "results": results,
    }
