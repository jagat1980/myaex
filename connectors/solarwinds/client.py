"""SolarWinds Observability SaaS read-only REST client."""

import asyncio
import logging
import os
import random
from typing import Any
import httpx

logger = logging.getLogger("connector.solarwinds.client")


class SolarWindsReadOnlyTransport(httpx.AsyncHTTPTransport):
    """Custom HTTPX transport enforcing Hard Safety Rule 3: strictly read-only GET requests."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        assert (
            request.method == "GET"
        ), f"Violation of Hard Safety Rule 3: Method {request.method} is strictly forbidden on source systems!"
        return await super().handle_async_request(request)


class SolarWindsSaaSClient:
    """Async read-only client for SolarWinds Observability SaaS."""

    def __init__(
        self,
        base_url: str | None = None,
        api_token: str | None = None,
        max_retries: int = 4,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv("SOLARWINDS_API_URL")
            or "https://api.eu-01.cloud.solarwinds.com"
        ).rstrip("/")
        self.api_token = api_token or os.getenv("SOLARWINDS_API_TOKEN", "")
        self.max_retries = max_retries

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(10.0, read=30.0),
            transport=SolarWindsReadOnlyTransport(),
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "SolarWindsSaaSClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def _get_with_retry(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform a GET request with exponential backoff on 429 and 5xx errors."""
        url = endpoint if endpoint.startswith("http") else f"{self.base_url}/{endpoint.lstrip('/')}"
        delay = 1.0

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.get(url, params=params)
                if response.status_code == 200:
                    return response.json()  # type: ignore[no-any-return]

                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt == self.max_retries:
                        response.raise_for_status()

                    retry_after = response.headers.get("Retry-After")
                    sleep_time = float(retry_after) if retry_after and retry_after.isdigit() else delay + random.uniform(0.1, 0.5)
                    logger.warning(
                        "Received status %d from SolarWinds API, retrying in %.2fs (attempt %d/%d)...",
                        response.status_code,
                        sleep_time,
                        attempt + 1,
                        self.max_retries,
                    )
                    await asyncio.sleep(sleep_time)
                    delay *= 2
                    continue

                response.raise_for_status()

            except (httpx.TransportError, httpx.TimeoutException) as exc:
                if attempt == self.max_retries:
                    raise
                sleep_time = delay + random.uniform(0.1, 0.5)
                logger.warning(
                    "Network error connecting to SolarWinds API (%s), retrying in %.2fs...",
                    exc,
                    sleep_time,
                )
                await asyncio.sleep(sleep_time)
                delay *= 2

        raise RuntimeError(f"Failed to fetch data from {url} after {self.max_retries} retries")

    async def list_entities(
        self,
        entity_type: str = "host",
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """List all entities of a given type from SolarWinds Observability SaaS.
        
        Paginates until all entities are retrieved.
        """
        entities: list[dict[str, Any]] = []
        next_page_token: str | None = None

        while True:
            params: dict[str, Any] = {
                "type": entity_type,
                "pageSize": page_size,
            }
            if next_page_token:
                params["pageToken"] = next_page_token

            data = await self._get_with_retry("/v1/entities", params=params)
            
            # SolarWinds SaaS entities can be in 'entities', 'items', or 'data'
            page_items = data.get("entities") or data.get("items") or data.get("data") or []
            if isinstance(page_items, list):
                entities.extend(page_items)

            next_page_token = data.get("nextPageToken") or data.get("next_token")
            if not next_page_token or len(page_items) == 0:
                break

        return entities
