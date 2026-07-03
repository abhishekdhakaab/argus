resource "google_secret_manager_secret" "jwt_private" {
  secret_id = "argus-jwt-private-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "jwt_private" {
  secret      = google_secret_manager_secret.jwt_private.id
  secret_data = var.jwt_private_key
}

resource "google_secret_manager_secret" "jwt_public" {
  secret_id = "argus-jwt-public-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "jwt_public" {
  secret      = google_secret_manager_secret.jwt_public.id
  secret_data = var.jwt_public_key
}
