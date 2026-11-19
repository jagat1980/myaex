"""Unit tests for the Temporal Graph Writer and Neo4j Cypher generation."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
import uuid
import pytest
from connectors.common.models import NormalisedRelation
from resolver.models import ResolvedEntity
from writer.graph_writer import TemporalGraphWriter, clean_attributes
from writer.reconcile import reconcile_stale_cis


def test_clean_attributes():
    raw = {
        "str_val": "test",
        "int_val": 42,
        "float_val": 3.14,
        "bool_val": True,
        "none_val": None,
        "list_val": ["a", "b", "c"],
        "tags": {"env": "prod", "tier": 1},
    }
    cleaned = clean_attributes(raw)
    assert cleaned["str_val"] == "test"
    assert cleaned["int_val"] == 42
    assert cleaned["float_val"] == 3.14
    assert cleaned["bool_val"] is True
    assert "none_val" not in cleaned
    assert cleaned["list_val"] == ["a", "b", "c"]
    assert cleaned["tags_env"] == "prod"
    assert cleaned["tags_tier"] == 1


def test_graph_writer_batching():
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    writer = TemporalGraphWriter(driver=mock_driver, batch_size=10)

    # Create 2 resolved entities with relations
    ci_id = uuid.uuid4()
    entities = [
        ResolvedEntity(
            tenant_id="t1",
            ci_id=ci_id,
            uid=f"t1:{ci_id}",
            kind="VM",
            canonical_name="mypcpoc",
            source_system="azure",
            source_id="vm-1",
            confidence=1.0,
            ip="10.0.0.4",
            attributes={"size": "D4s_v3"},
            relations=[
                NormalisedRelation(
                    type="CONNECTS_TO",
                    target_source_system="azure",
                    target_source_id="nic-1",
                    target_kind="NIC",
                ),
                NormalisedRelation(
                    type="DEPENDS_ON",
                    target_source_system="azure",
                    target_source_id="disk-1",
                    target_kind="Disk",
                ),
            ],
            observed_at=datetime.now(timezone.utc),
        )
    ]

    metrics = writer.write_entities(entities)
    assert metrics["nodes"] == 1
    assert metrics["edges"] == 2

    # Verify session execute_write was invoked for nodes and edges
    assert mock_session.execute_write.call_count >= 3


def test_reconcile_stale_cis():
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    mock_record = {"stale_count": 3}
    mock_session.execute_write.return_value = mock_record

    count = reconcile_stale_cis(mock_driver, tenant_id="t1", staleness_minutes=60)
    assert count == 3
    assert mock_session.execute_write.called
