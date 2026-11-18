resource "azurerm_postgresql_flexible_server" "postgres" {
  name                          = "psql-${var.project}-${var.environment}-${random_string.suffix.result}"
  resource_group_name           = azurerm_resource_group.rg.name
  location                      = azurerm_resource_group.rg.location
  version                       = "16"
  delegated_subnet_id           = azurerm_subnet.postgres.id
  private_dns_zone_id           = azurerm_private_dns_zone.postgres.id
  administrator_login           = "cgadmin"
  administrator_password        = random_password.postgres_password.result
  sku_name                      = var.postgres_sku_name
  storage_mb                    = var.postgres_storage_mb
  zone                          = "1"
  public_network_access_enabled = false
  tags                          = var.tags

  lifecycle {
    ignore_changes = [zone, high_availability]
  }

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]
}

# Enable pgvector extension on the Flexible Server instance
resource "azurerm_postgresql_flexible_server_configuration" "pgvector" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.postgres.id
  value     = "VECTOR"
}

resource "azurerm_postgresql_flexible_server_database" "contextgraph" {
  name      = "contextgraph"
  server_id = azurerm_postgresql_flexible_server.postgres.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}
