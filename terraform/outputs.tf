output "gateway_url" {
  value = google_cloud_run_v2_service.gateway.uri
}

output "cloud_sql_connection_name" {
  value = google_sql_database_instance.argus.connection_name
}

output "redis_host" {
  value = google_redis_instance.argus.host
}

output "raw_documents_bucket" {
  value = google_storage_bucket.raw_documents.name
}
