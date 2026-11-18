variable "project" {
  type        = string
  default     = "contextgraph"
  description = "Project name prefix for resources"
}

variable "environment" {
  type        = string
  default     = "nonprod"
  description = "Environment identifier (nonprod, staging, etc.)"
}

variable "location" {
  type        = string
  default     = "uksouth"
  description = "Azure region for deployment"
}

variable "vnet_cidr" {
  type        = string
  default     = "10.240.0.0/16"
  description = "Virtual Network address space"
}

variable "aks_subnet_cidr" {
  type        = string
  default     = "10.240.0.0/20"
  description = "Subnet CIDR for AKS nodes and pods (Azure CNI)"
}

variable "postgres_subnet_cidr" {
  type        = string
  default     = "10.240.16.0/24"
  description = "Subnet CIDR delegated to Azure PostgreSQL Flexible Server"
}

variable "aks_node_vm_size" {
  type        = string
  default     = "Standard_D4s_v5"
  description = "VM SKU for AKS system node pool (4 vCPU, 16 GiB RAM)"
}

variable "aks_node_count" {
  type        = number
  default     = 2
  description = "Number of worker nodes in AKS system node pool"
}

variable "postgres_sku_name" {
  type        = string
  default     = "B_Standard_B2s"
  description = "Compute SKU for PostgreSQL Flexible Server"
}

variable "postgres_storage_mb" {
  type        = number
  default     = 32768
  description = "Storage capacity in MB for PostgreSQL Flexible Server"
}

variable "github_owner" {
  type        = string
  default     = "jagat1980"
  description = "GitHub account or organization name for OIDC federation"
}

variable "github_repository_name" {
  type        = string
  default     = "myaex"
  description = "GitHub repository name"
}

variable "tags" {
  type = map(string)
  default = {
    Project     = "context-graph"
    Environment = "non-prod"
    ManagedBy   = "terraform"
    Stage       = "poc"
  }
  description = "Common resource tags"
}
