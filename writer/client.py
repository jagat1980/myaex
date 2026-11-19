"""Neo4j driver client and transaction runner for the graph writer."""

import logging
import os
from typing import Any
from neo4j import GraphDatabase, Driver

logger = logging.getLogger("writer.client")


class Neo4jWriterClient:
    """Manages connection and write transactions to Neo4j Community Edition."""

    def __init__(
        self,
        uri: str | None = None,
        auth_file: str | None = None,
    ) -> None:
        self.uri = (
            uri
            or os.getenv("NEO4J_URI")
            or "bolt://context-graph.context-graph.svc.cluster.local:7687"
        )
        self.auth_file = (
            auth_file
            or os.getenv("NEO4J_AUTH_FILE", "/mnt/secrets-store/neo4j-auth")
        )
        self._driver: Driver | None = None

    def _get_credentials(self) -> tuple[str, str]:
        """Parse username and password from environment or Key Vault CSI secret file."""
        auth_raw = os.getenv("NEO4J_AUTH", "")

        if not auth_raw and os.path.exists(self.auth_file):
            try:
                with open(self.auth_file, "r", encoding="utf-8") as f:
                    auth_raw = f.read().strip()
            except Exception as exc:
                logger.warning("Could not read auth file %s: %s", self.auth_file, exc)

        if "/" in auth_raw:
            user, password = auth_raw.split("/", 1)
            return user.strip(), password.strip()

        user = os.getenv("NEO4J_USER", "neo4j")
        password = auth_raw or os.getenv("NEO4J_PASSWORD", "")
        return user.strip(), password.strip()

    def get_driver(self) -> Driver:
        """Initialize or return the cached Neo4j official driver."""
        if self._driver is None:
            user, password = self._get_credentials()
            logger.info("Connecting to Neo4j at %s with user %s", self.uri, user)
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(user, password),
                max_connection_lifetime=30 * 60,
                max_connection_pool_size=10,
                connection_acquisition_timeout=15.0,
            )
        return self._driver

    def close(self) -> None:
        """Close driver connection pool."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def __enter__(self) -> "Neo4jWriterClient":
        self.get_driver()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
