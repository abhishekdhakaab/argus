locals {
  cloud_sql_annotation = {
    "run.googleapis.com/cloudsql-instances" = google_sql_database_instance.argus.connection_name
  }
}

resource "google_cloud_run_v2_service" "mcp_rag" {
  name     = "argus-mcp-rag"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.cloud_run.email
    annotations     = local.cloud_sql_annotation

    vpc_access {
      connector = google_vpc_access_connector.argus.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = var.rag_image

      ports {
        container_port = 8080
      }

      env {
        name  = "DATABASE_URL"
        value = local.psycopg_database_url
      }
      env {
        name  = "HF_HUB_DISABLE_XET"
        value = "1"
      }
    }
  }

  depends_on = [google_sql_database.argus, google_sql_user.argus]
}

resource "google_cloud_run_v2_service" "mcp_sql" {
  name     = "argus-mcp-sql"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.cloud_run.email
    annotations     = local.cloud_sql_annotation

    vpc_access {
      connector = google_vpc_access_connector.argus.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = var.sql_image

      ports {
        container_port = 8080
      }

      env {
        name  = "DATABASE_URL"
        value = local.sql_database_url
      }
    }
  }

  depends_on = [google_sql_database.argus, google_sql_user.argus]
}

resource "google_cloud_run_v2_service" "mcp_api" {
  name     = "argus-mcp-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.cloud_run.email

    vpc_access {
      connector = google_vpc_access_connector.argus.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = var.external_api_image

      ports {
        container_port = 8080
      }

      env {
        name  = "REDIS_URL"
        value = local.redis_url
      }
    }
  }

  depends_on = [google_redis_instance.argus]
}

resource "google_cloud_run_v2_service" "gateway" {
  name     = "argus-gateway"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.cloud_run.email
    annotations     = local.cloud_sql_annotation

    vpc_access {
      connector = google_vpc_access_connector.argus.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = var.gateway_image

      ports {
        container_port = 8080
      }

      env {
        name  = "DATABASE_URL"
        value = local.async_database_url
      }
      env {
        name  = "REDIS_URL"
        value = local.redis_url
      }
      env {
        name  = "DOC_MCP_URL"
        value = google_cloud_run_v2_service.mcp_rag.uri
      }
      env {
        name  = "SQL_MCP_URL"
        value = google_cloud_run_v2_service.mcp_sql.uri
      }
      env {
        name  = "EXTERNAL_API_MCP_URL"
        value = google_cloud_run_v2_service.mcp_api.uri
      }
      env {
        name  = "JWT_PRIVATE_KEY_PATH"
        value = "/secrets/jwt-private/private.pem"
      }
      env {
        name  = "JWT_PUBLIC_KEY_PATH"
        value = "/secrets/jwt-public/public.pem"
      }

      volume_mounts {
        name       = "jwt-private"
        mount_path = "/secrets/jwt-private"
      }
      volume_mounts {
        name       = "jwt-public"
        mount_path = "/secrets/jwt-public"
      }
    }

    volumes {
      name = "jwt-private"

      secret {
        secret = google_secret_manager_secret.jwt_private.secret_id

        items {
          version = "latest"
          path    = "private.pem"
        }
      }
    }
    volumes {
      name = "jwt-public"

      secret {
        secret = google_secret_manager_secret.jwt_public.secret_id

        items {
          version = "latest"
          path    = "public.pem"
        }
      }
    }
  }

  depends_on = [
    google_cloud_run_v2_service.mcp_rag,
    google_cloud_run_v2_service.mcp_sql,
    google_cloud_run_v2_service.mcp_api,
    google_secret_manager_secret_version.jwt_private,
    google_secret_manager_secret_version.jwt_public,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "gateway_public" {
  name     = google_cloud_run_v2_service.gateway.name
  location = google_cloud_run_v2_service.gateway.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
