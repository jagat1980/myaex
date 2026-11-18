# tfsec:ignore:azure-container-limit-authorized-ips Cluster API access is accessible to non-prod developers; IP restrictions can be layered via enterprise ingress.
# tfsec:ignore:azure-container-logging OMS agent logging is optional in non-prod POC cluster.
resource "azurerm_kubernetes_cluster" "aks" {
  name                = "aks-${var.project}-${var.environment}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  dns_prefix          = "aks-${var.project}-${var.environment}"

  # Zero-trust security & RBAC enforcement
  role_based_access_control_enabled = true
  oidc_issuer_enabled               = true
  workload_identity_enabled         = true

  network_profile {
    network_plugin    = "azure"
    network_policy    = "azure"
    load_balancer_sku = "standard"
  }

  default_node_pool {
    name            = "system"
    node_count      = var.aks_node_count
    vm_size         = var.aks_node_vm_size
    vnet_subnet_id  = azurerm_subnet.aks.id
    os_disk_size_gb = 128
    os_disk_type    = "Managed"
    tags            = var.tags
  }

  identity {
    type = "SystemAssigned"
  }

  key_vault_secrets_provider {
    secret_rotation_enabled  = true
    secret_rotation_interval = "5m"
  }

  tags = var.tags
}
