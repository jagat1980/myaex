resource "azurerm_user_assigned_identity" "uami" {
  name                = "uami-${var.project}-${var.environment}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  tags                = var.tags
}

# Grant subscription reader access for Azure Resource Graph connector
resource "azurerm_role_assignment" "uami_subscription_reader" {
  scope                = "/subscriptions/${data.azurerm_client_config.current.subscription_id}"
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.uami.principal_id
}

# Grant Key Vault Secrets User role to UAMI for CSI driver and connector access
resource "azurerm_role_assignment" "uami_keyvault_secrets_user" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.uami.principal_id
}

# Workload Identity Federation: bind Kubernetes context-graph-sa to Azure UAMI
resource "azurerm_federated_identity_credential" "aks_fic" {
  name                = "fic-${var.project}-sa"
  resource_group_name = azurerm_resource_group.rg.name
  parent_id           = azurerm_user_assigned_identity.uami.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.aks.oidc_issuer_url
  subject             = "system:serviceaccount:context-graph:context-graph-sa"
}

# ------------------------------------------------------------------------------
# GitHub Actions CI/CD Keyless OIDC Workload Identity Federation
# ------------------------------------------------------------------------------

# Dedicated Managed Identity for GitHub Actions CI/CD workflows
resource "azurerm_user_assigned_identity" "github_actions" {
  name                = "uami-github-actions-${var.environment}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  tags                = var.tags
}

# Federated Credential for Main Branch (Pushes & Merges)
resource "azurerm_federated_identity_credential" "gh_actions_main" {
  name                = "fic-gh-main"
  resource_group_name = azurerm_resource_group.rg.name
  parent_id           = azurerm_user_assigned_identity.github_actions.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = "https://token.actions.githubusercontent.com"
  subject             = "repo:${var.github_owner}/${var.github_repository_name}:ref:refs/heads/main"
}

# Federated Credential for Pull Requests (PR Validation & Plan)
resource "azurerm_federated_identity_credential" "gh_actions_pr" {
  name                = "fic-gh-pr"
  resource_group_name = azurerm_resource_group.rg.name
  parent_id           = azurerm_user_assigned_identity.github_actions.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = "https://token.actions.githubusercontent.com"
  subject             = "repo:${var.github_owner}/${var.github_repository_name}:pull_request"
}

# Scoped RBAC Roles for GitHub Actions

# Contributor on Resource Group to manage cloud infrastructure
resource "azurerm_role_assignment" "gh_actions_rg_contributor" {
  scope                = azurerm_resource_group.rg.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.github_actions.principal_id
}

# AcrPush on ACR to build and push container images
resource "azurerm_role_assignment" "gh_actions_acr_push" {
  scope                = azurerm_container_registry.acr.id
  role_definition_name = "AcrPush"
  principal_id         = azurerm_user_assigned_identity.github_actions.principal_id
}

# AKS Cluster User to fetch cluster credentials and deploy manifests
resource "azurerm_role_assignment" "gh_actions_aks_user" {
  scope                = azurerm_kubernetes_cluster.aks.id
  role_definition_name = "Azure Kubernetes Service Cluster User Role"
  principal_id         = azurerm_user_assigned_identity.github_actions.principal_id
}
