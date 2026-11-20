"""Vector store and 768-dimensional embedding generation for pgvector."""

import hashlib
import json
import math
import re
from typing import Any
import uuid
import asyncpg
from risk.models import SearchResult, VectorDocument


def generate_embedding(text: str, dim: int = 768) -> list[float]:
    """Generate a deterministic, unit-normalized 768-dimensional semantic embedding.
    
    Uses sub-linear term frequency hashing and projection to provide semantic
    similarity across overlapping vocabularies with zero external network dependencies.
    """
    if not text or not text.strip():
        # Return zero vector if text is empty
        return [0.0] * dim

    words = re.findall(r"\b[a-zA-Z0-9_\-\.]{2,}\b", text.lower())
    if not words:
        words = [text.lower().strip()]

    # Also extract character 3-grams and 4-grams for subword matching
    features: dict[str, float] = {}
    for w in words:
        features[w] = features.get(w, 0.0) + 1.0
        if len(w) >= 4:
            for i in range(len(w) - 3):
                gram = w[i : i + 3]
                features[f"g3_{gram}"] = features.get(f"g3_{gram}", 0.0) + 0.5

    vec = [0.0] * dim
    for feat, count in features.items():
        weight = 1.0 + math.log(count)
        # Hash feature to 4 independent coordinate dimensions for dense representation
        h = hashlib.sha256(feat.encode("utf-8")).digest()
        for idx in range(4):
            chunk = h[idx * 4 : (idx + 1) * 4]
            coord = int.from_bytes(chunk, byteorder="big") % dim
            sign = 1.0 if (h[16 + idx] % 2 == 0) else -1.0
            vec[coord] += sign * weight

    # Normalize to unit length (L2 norm = 1.0)
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0.0:
        vec = [round(x / norm, 6) for x in vec]
    else:
        vec = [0.0] * dim

    return vec


def format_pgvector(embedding: list[float]) -> str:
    """Format a float list into PostgreSQL pgvector literal string '[v1,v2,...]'."""
    return "[" + ",".join(str(x) for x in embedding) + "]"


class VectorStore:
    """Manages pgvector persistence and cosine similarity queries."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn

    async def upsert_document(self, doc: VectorDocument) -> int:
        """Insert or replace a remediation intelligence document with its 768-dim embedding."""
        combined_text = f"{doc.title}\n{doc.content}"
        embedding = generate_embedding(combined_text, dim=768)
        pg_vec_str = format_pgvector(embedding)

        meta = dict(doc.metadata)
        meta["doc_id"] = doc.doc_id
        meta["title"] = doc.title
        meta_json = json.dumps(meta, sort_keys=True)

        # Delete any prior document with identical doc_id for this tenant to ensure idempotence
        await self.conn.execute(
            """
            DELETE FROM embeddings
            WHERE tenant_id = $1 AND metadata->>'doc_id' = $2;
            """,
            doc.tenant_id,
            doc.doc_id,
        )

        row = await self.conn.fetchrow(
            """
            INSERT INTO embeddings (
                tenant_id, ci_id, service_name, doc_type, content, embedding, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6::vector, $7::jsonb)
            RETURNING id;
            """,
            doc.tenant_id,
            doc.ci_id,
            doc.service_name,
            doc.doc_type,
            doc.content,
            pg_vec_str,
            meta_json,
        )
        return int(row["id"])

    async def search_similar(
        self,
        tenant_id: str,
        query_text: str,
        doc_type: str | None = None,
        ci_id: uuid.UUID | None = None,
        k: int = 5,
    ) -> list[SearchResult]:
        """Execute pgvector cosine distance similarity search."""
        query_vec = generate_embedding(query_text, dim=768)
        pg_vec_str = format_pgvector(query_vec)

        rows = await self.conn.fetch(
            """
            SELECT id, tenant_id, ci_id, service_name, doc_type, content, metadata,
                   1.0 - (embedding <=> $1::vector) AS similarity
            FROM embeddings
            WHERE tenant_id = $2
              AND ($3::varchar IS NULL OR doc_type = $3)
              AND ($4::uuid IS NULL OR ci_id = $4)
            ORDER BY embedding <=> $1::vector
            LIMIT $5;
            """,
            pg_vec_str,
            tenant_id,
            doc_type,
            ci_id,
            k,
        )

        results: list[SearchResult] = []
        for r in rows:
            meta = r["metadata"]
            if isinstance(meta, str):
                meta = json.loads(meta)
            results.append(
                SearchResult(
                    id=int(r["id"]),
                    tenant_id=str(r["tenant_id"]),
                    ci_id=uuid.UUID(str(r["ci_id"])) if r["ci_id"] else None,
                    service_name=r["service_name"],
                    doc_type=str(r["doc_type"]),
                    content=str(r["content"]),
                    metadata=meta or {},
                    similarity=round(float(r["similarity"]), 4),
                )
            )
        return results
