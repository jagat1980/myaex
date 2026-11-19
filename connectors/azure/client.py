"""Azure Resource Graph read-only client using Azure Workload Identity."""

from typing import Any
from azure.identity import DefaultAzureCredential
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions


class AzureResourceGraphReader:
    """Read-only client querying Azure Resource Graph via Azure Workload Identity."""

    def __init__(self, subscription_ids: list[str]) -> None:
        self.subscription_ids = subscription_ids
        self.credential = DefaultAzureCredential()
        self.client = ResourceGraphClient(self.credential)

    def query(self, kql_query: str) -> list[dict[str, Any]]:
        """Execute a read-only KQL query against Azure Resource Graph.

        Hard Safety Rule 3: Only queries reading resource state are allowed.
        """
        request_options = QueryRequestOptions(result_format="objectArray")
        request = QueryRequest(
            subscriptions=self.subscription_ids,
            query=kql_query,
            options=request_options,
        )
        response = self.client.resources(request)
        if hasattr(response, "data") and isinstance(response.data, list):
            return list(response.data)
        return []
