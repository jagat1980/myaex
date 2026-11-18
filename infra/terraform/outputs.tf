output "resource_group_name" {
  description = "Name of the provisioned Azure Resource Group"
  value       = azurerm_resource_group.rg.name
}

output "location" {
  description = "Azure region of deployment"
  value       = azurerm_resource_group.rg.location
}

output "allowed_kube_context" {
  description = "Kubernetes context name for inputs.yaml platform.allowed_kube_context"
  value       = azurerm_kubernetes_cluster.aks.name
}

output "aks_cluster_name" {
  description = "Name of the provisioned AKS cluster"
  value       = azurerm_kubernetes_cluster.aks.name
}

output "secret_store_name" {
  description = "Azure Key Vault name for inputs.yaml platform.secret_store_name"
  value       = azurerm_key_vault.kv.name
}

output "container_registry" {
  description = "ACR login server for inputs.yaml platform.container_registry"
  value       = azurerm_container_registry.acr.login_server
}

output "postgres_host" {
  description = "PostgreSQL Flexible Server FQDN for inputs.yaml postgres.host"
  value       = azurerm_postgresql_flexible_server.postgres.fqdn
}

output "postgres_database" {
  description = "PostgreSQL database name for inputs.yaml postgres.database"
  value       = azurerm_postgresql_flexible_server_database.contextgraph.name
}

output "postgres_user_secret_name" {
  description = "Secret name in Key Vault holding PostgreSQL credentials"
  value       = azurerm_key_vault_secret.postgres_auth.name
}

output "uami_client_id" {
  description = "Client ID of the User-Assigned Managed Identity for Workload Identity"
  value       = azurerm_user_assigned_identity.uami.client_id
}

output "vnet_cidr" {
  description = "VNet CIDR for inputs.yaml mcp.aex_gateway_cidr"
  value       = var.vnet_cidr
}

output "github_actions_client_id" {
  description = "Client ID of the GitHub Actions Managed Identity for AZURE_CLIENT_ID secret"
  value       = azurerm_user_assigned_identity.github_actions.client_id
}

output "azure_subscription_id" {
  description = "Azure Subscription ID for AZURE_SUBSCRIPTION_ID secret"
  value       = data.azurerm_client_config.current.subscription_id
}

output "azure_tenant_id" {
  description = "Azure Entra ID Tenant ID for AZURE_TENANT_ID secret"
  value       = data.azurerm_client_config.current.tenant_id
}
