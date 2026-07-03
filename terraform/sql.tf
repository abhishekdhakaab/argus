resource "google_sql_database_instance" "argus" {
  name             = "argus-db"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier              = "db-f1-micro"
    availability_type = "ZONAL"
    disk_size         = 20
    disk_type         = "PD_SSD"

    ip_configuration {
      ipv4_enabled = true
    }
  }

  deletion_protection = true

  depends_on = [google_project_service.required]
}

resource "google_sql_database" "argus" {
  name     = var.db_name
  instance = google_sql_database_instance.argus.name
}

resource "google_sql_user" "argus" {
  name     = var.db_user
  instance = google_sql_database_instance.argus.name
  password = var.db_password
}

locals {
  cloud_sql_socket_host = "/cloudsql/${google_sql_database_instance.argus.connection_name}"
  async_database_url    = "postgresql+asyncpg://${var.db_user}:${var.db_password}@/${var.db_name}?host=${local.cloud_sql_socket_host}"
  psycopg_database_url  = "postgresql+psycopg2://${var.db_user}:${var.db_password}@/${var.db_name}?host=${local.cloud_sql_socket_host}"
  sql_database_url      = "postgresql://${var.db_user}:${var.db_password}@/${var.db_name}?host=${local.cloud_sql_socket_host}"
}
