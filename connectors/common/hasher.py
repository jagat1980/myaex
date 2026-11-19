"""Deterministic hashing for raw record payloads and deduplication."""

import hashlib
import json
from typing import Any


def compute_content_hash(payload: dict[str, Any] | list[Any]) -> str:
    """Compute a deterministic SHA-256 hash of a JSON-serializable dictionary.

    Sorts keys to ensure identical payloads produce identical hashes regardless
    of key ordering.
    """
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
