"""Unit tests for 768-dimensional embeddings, pgvector operations, and intelligence loader."""

import math
from unittest.mock import AsyncMock
import uuid
import pytest
from risk.loader import SEED_DOCUMENTS, load_seed_documents
from risk.models import VectorDocument
from risk.vectors import VectorStore, format_pgvector, generate_embedding


def test_generate_embedding_dimension_and_norm():
    text = "Windows Server disk space critical alert"
    vec = generate_embedding(text, dim=768)

    assert len(vec) == 768
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-4


def test_generate_embedding_empty_text():
    vec = generate_embedding("", dim=768)
    assert len(vec) == 768
    assert all(x == 0.0 for x in vec)


def test_generate_embedding_determinism():
    text = "C: drive 100% full due to CBS log archive"
    vec1 = generate_embedding(text, dim=768)
    vec2 = generate_embedding(text, dim=768)
    assert vec1 == vec2


def test_semantic_similarity_relative_ordering():
    """Verify that semantically related texts have higher cosine similarity than unrelated texts."""
    doc1 = generate_embedding("Windows OS disk space exhausted CBS log temp files", dim=768)
    doc2_related = generate_embedding("Runbook to clean Windows CBS logs and free disk space", dim=768)
    doc3_unrelated = generate_embedding("Kubernetes container memory limit exceeded in pod", dim=768)

    # Dot product of unit vectors equals cosine similarity
    sim_related = sum(a * b for a, b in zip(doc1, doc2_related))
    sim_unrelated = sum(a * b for a, b in zip(doc1, doc3_unrelated))

    assert sim_related > sim_unrelated
    assert sim_related > 0.35


def test_format_pgvector():
    vec = [0.123, -0.456, 0.789]
    formatted = format_pgvector(vec)
    assert formatted == "[0.123,-0.456,0.789]"


@pytest.mark.asyncio
async def test_vector_store_upsert():
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {"id": 42}

    store = VectorStore(mock_conn)
    doc = VectorDocument(
        tenant_id="t1",
        doc_id="INC-1001",
        doc_type="incident",
        title="Disk Space Alert",
        content="C: drive full",
        metadata={"severity": "P1"},
    )

    doc_id = await store.upsert_document(doc)
    assert doc_id == 42
    assert mock_conn.execute.called  # DELETE prior check
    assert mock_conn.fetchrow.called  # INSERT check


@pytest.mark.asyncio
async def test_vector_store_search_similar():
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [
        {
            "id": 1,
            "tenant_id": "t1",
            "ci_id": str(uuid.uuid4()),
            "service_name": "CoreInfra",
            "doc_type": "incident",
            "content": "C: drive full",
            "metadata": '{"severity": "P1"}',
            "similarity": 0.8876,
        }
    ]

    store = VectorStore(mock_conn)
    results = await store.search_similar(
        tenant_id="t1",
        query_text="disk cleanup",
        doc_type="incident",
        k=3,
    )

    assert len(results) == 1
    assert results[0].doc_type == "incident"
    assert results[0].similarity == 0.8876
    assert results[0].metadata["severity"] == "P1"


@pytest.mark.asyncio
async def test_load_seed_documents():
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {"id": 1}

    count = await load_seed_documents(mock_conn, tenant_id="t1")
    assert count == len(SEED_DOCUMENTS)
    assert count == 12
