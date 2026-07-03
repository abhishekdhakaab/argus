variable "project_id" {
  description = "GCP project ID that will host Argus."
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run, Cloud SQL, Redis, and storage."
  type        = string
  default     = "us-central1"
}

variable "db_name" {
  description = "Postgres database name."
  type        = string
  default     = "argus"
}

variable "db_user" {
  description = "Postgres application user."
  type        = string
  default     = "argus"
}

variable "db_password" {
  description = "Postgres application password."
  type        = string
  sensitive   = true
}

variable "jwt_private_key" {
  description = "RS256 private key PEM for gateway JWT signing."
  type        = string
  sensitive   = true
}

variable "jwt_public_key" {
  description = "RS256 public key PEM for gateway JWT verification."
  type        = string
  sensitive   = true
}

variable "gateway_image" {
  description = "Container image for the FastAPI gateway."
  type        = string
}

variable "rag_image" {
  description = "Container image for the RAG MCP server."
  type        = string
}

variable "sql_image" {
  description = "Container image for the SQL MCP server."
  type        = string
}

variable "external_api_image" {
  description = "Container image for the external API MCP server."
  type        = string
}
