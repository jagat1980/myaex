data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 5
  special = false
  upper   = false
}

resource "azurerm_key_vault" "kv" {
  name                       = "kv-cg-${var.environment}-${random_string.suffix.result}"
  location                   = azurerm_resource_group.rg.location
  resource_group_name        = azurerm_resource_group.rg.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  enable_rbac_authorization  = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = true

  # tfsec:ignore:azure-keyvault-specify-network-acl Allow network access for non-prod bootstrap and GitHub Actions runners
  network_acls {
    bypass                     = "AzureServices"
    default_action             = "Allow"
    virtual_network_subnet_ids = [azurerm_subnet.aks.id]
  }

  tags = var.tags
}

# Grant the deploying principal Secrets Officer rights to populate bootstrap secrets
resource "azurerm_role_assignment" "deployer_kv_secrets_officer" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# Auto-generated credentials for internal data stores
resource "random_password" "neo4j_password" {
  length           = 24
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "random_password" "postgres_password" {
  length  = 24
  special = false
}

# tfsec:ignore:azure-keyvault-ensure-secret-expiry Standing cluster infrastructure credential
resource "azurerm_key_vault_secret" "neo4j_auth" {
  name         = "neo4j-auth"
  value        = random_password.neo4j_password.result
  content_type = "text/plain"
  key_vault_id = azurerm_key_vault.kv.id
  depends_on   = [azurerm_role_assignment.deployer_kv_secrets_officer]
}

# tfsec:ignore:azure-keyvault-ensure-secret-expiry Standing cluster infrastructure credential
resource "azurerm_key_vault_secret" "postgres_auth" {
  name         = "postgres-auth"
  content_type = "application/json"
  value = jsonencode({
    username = "cgadmin"
    password = random_password.postgres_password.result
    host     = azurerm_postgresql_flexible_server.postgres.fqdn
    database = "contextgraph"
    port     = 5432
  })
  key_vault_id = azurerm_key_vault.kv.id
  depends_on   = [azurerm_role_assignment.deployer_kv_secrets_officer]
}

# Seeded placeholders for external source systems (values filled securely in Key Vault)
# tfsec:ignore:azure-keyvault-ensure-secret-expiry Managed external credential
resource "azurerm_key_vault_secret" "itsm_credentials" {
  name         = "itsm-credentials"
  value        = "PLACEHOLDER_SET_IN_KEYVAULT"
  content_type = "text/plain"
  key_vault_id = azurerm_key_vault.kv.id
  depends_on   = [azurerm_role_assignment.deployer_kv_secrets_officer]
}

# tfsec:ignore:azure-keyvault-ensure-secret-expiry Managed external credential
resource "azurerm_key_vault_secret" "solarwinds_credentials" {
  name         = "solarwinds-credentials"
  value        = "PLACEHOLDER_SET_IN_KEYVAULT"
  content_type = "text/plain"
  key_vault_id = azurerm_key_vault.kv.id
  depends_on   = [azurerm_role_assignment.deployer_kv_secrets_officer]
}

# tfsec:ignore:azure-keyvault-ensure-secret-expiry Managed external credential
resource "azurerm_key_vault_secret" "azure_credentials" {
  name         = "azure-credentials"
  value        = "PLACEHOLDER_SET_IN_KEYVAULT"
  content_type = "text/plain"
  key_vault_id = azurerm_key_vault.kv.id
  depends_on   = [azurerm_role_assignment.deployer_kv_secrets_officer]
}

# tfsec:ignore:azure-keyvault-ensure-secret-expiry Managed external credential
resource "azurerm_key_vault_secret" "bigfix_credentials" {
  name         = "bigfix-credentials"
  value        = "PLACEHOLDER_SET_IN_KEYVAULT"
  content_type = "text/plain"
  key_vault_id = azurerm_key_vault.kv.id
  depends_on   = [azurerm_role_assignment.deployer_kv_secrets_officer]
}

# tfsec:ignore:azure-keyvault-ensure-secret-expiry Managed external credential
resource "azurerm_key_vault_secret" "veeam_credentials" {
  name         = "veeam-credentials"
  value        = "PLACEHOLDER_SET_IN_KEYVAULT"
  content_type = "text/plain"
  key_vault_id = azurerm_key_vault.kv.id
  depends_on   = [azurerm_role_assignment.deployer_kv_secrets_officer]
}

# tfsec:ignore:azure-keyvault-ensure-secret-expiry Managed external credential
resource "azurerm_key_vault_secret" "mcp_auth_token" {
  name         = "mcp-auth-token"
  value        = "PLACEHOLDER_SET_IN_KEYVAULT"
  content_type = "text/plain"
  key_vault_id = azurerm_key_vault.kv.id
  depends_on   = [azurerm_role_assignment.deployer_kv_secrets_officer]
}
